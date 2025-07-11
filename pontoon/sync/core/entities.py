import logging

from collections import defaultdict
from datetime import datetime
from os.path import exists, isfile, join, relpath, splitext
from typing import Optional

from moz.l10n.paths import L10nConfigPaths, L10nDiscoverPaths

from django.db import transaction
from django.db.models import Q

from pontoon.base.models import Entity, Locale, Project, Resource, TranslatedResource
from pontoon.sync.core.checkout import Checkout
from pontoon.sync.formats import parse_translations
from pontoon.sync.formats.common import ParseError, VCSTranslation


log = logging.getLogger(__name__)


def sync_entities_from_repo(
    project: Project,
    locale_map: dict[str, Locale],
    checkout: Checkout,
    paths: L10nConfigPaths | L10nDiscoverPaths,
    now: datetime,
) -> tuple[int, set[str], set[str]]:
    """(added_entities_count, changed_source_paths, removed_source_paths"""
    if not checkout.changed and not checkout.removed and not checkout.renamed:
        return 0, set(), set()
    log.info(f"[{project.slug}] Syncing entities from repo...")
    # db_path -> parsed_resource
    updates: dict[str, list[VCSTranslation]] = {}
    source_paths = set(paths.ref_paths)
    source_plurals = ["one", "other"]
    for co_path in checkout.changed:
        path = join(checkout.path, co_path)
        if path in source_paths and exists(path):
            db_path = get_db_path(paths, path)
            try:
                translations = parse_translations(path, gettext_plurals=source_plurals)
            except ParseError as error:
                log.error(
                    f"[{project.slug}:{db_path}] Skipping resource with parse error: {error}"
                )
                translations = []
            except ValueError as error:
                if str(error).startswith("Translation format"):
                    log.warning(
                        f"[{project.slug}:{db_path}] Skipping resource with unsupported format"
                    )
                    translations = []
                else:
                    raise error
            updates[db_path] = translations

    with transaction.atomic():
        renamed_paths = rename_resources(project, paths, checkout)
        removed_paths = remove_resources(project, paths, checkout)
        old_res_added_ent_count, changed_paths = update_resources(project, updates, now)
        new_res_added_ent_count, _ = add_resources(project, updates, changed_paths, now)
        update_translated_resources(project, locale_map, paths)

    return (
        old_res_added_ent_count + new_res_added_ent_count,
        renamed_paths | changed_paths,
        removed_paths,
    )


def rename_resources(
    project: Project, paths: L10nConfigPaths | L10nDiscoverPaths, checkout: Checkout
) -> set[str]:
    if not checkout.renamed:
        return set()
    renamed_db_paths = {
        get_db_path(paths, join(checkout.path, old_path)): get_db_path(
            paths, join(checkout.path, new_path)
        )
        for old_path, new_path in checkout.renamed
    }
    renamed_resources = project.resources.filter(path__in=renamed_db_paths.keys())
    for res in renamed_resources:
        new_db_path = renamed_db_paths[res.path]
        log.info(f"[{project.slug}:{res.path}] Rename as {new_db_path}")
        res.path = new_db_path
    Resource.objects.bulk_update(renamed_resources, ["path"])
    return set(renamed_db_paths.values())


def remove_resources(
    project: Project, paths: L10nConfigPaths | L10nDiscoverPaths, checkout: Checkout
) -> set[str]:
    if not checkout.removed:
        return set()
    removed_resources = project.resources.filter(
        path__in={
            get_db_path(paths, join(checkout.path, co_path))
            for co_path in checkout.removed
        }
    )
    removed_db_paths = {res.path for res in removed_resources}
    if removed_db_paths:
        # FIXME: https://github.com/mozilla/pontoon/issues/2133
        removed_resources.delete()
        rm_count = len(removed_db_paths)
        str_source_files = "source file" if rm_count == 1 else "source files"
        log.info(
            f"[{project.slug}] Removed {rm_count} {str_source_files}: {', '.join(removed_db_paths)}"
        )
    return removed_db_paths


def update_resources(
    project: Project,
    updates: dict[str, list[VCSTranslation]],
    now: datetime,
) -> tuple[int, set[str]]:
    changed_resources = (
        list(project.resources.filter(path__in=updates.keys())) if updates else None
    )
    if not changed_resources:
        return 0, set()
    log.info(
        f"[{project.slug}] Changed source files: {', '.join(res.path for res in changed_resources)}"
    )

    prev_entities: dict[tuple[str, str], Entity] = {
        (e.resource.path, e.key or e.string): e
        for e in Entity.objects.filter(resource__in=changed_resources, obsolete=False)
        .select_related("resource")
        .iterator()
    }
    next_entities: dict[tuple[str, str], Entity] = {
        (path, entity.key or entity.string): entity
        for path, entity in (
            (cr.path, entity_from_source(cr, now, 0, tx))
            for cr in changed_resources
            for tx in updates[cr.path]
        )
    }
    prev_not_next = prev_entities.keys() - next_entities.keys()
    prev_and_next = prev_entities.keys() & next_entities.keys()
    next_not_prev = next_entities.keys() - prev_entities.keys()

    obsolete_entities: list[Entity] = []
    log_rm: dict[str, list[str]] = defaultdict(list)
    for key, prev_ent in prev_entities.items():
        if key in prev_not_next:
            prev_ent.obsolete = True
            prev_ent.date_obsoleted = now
            obsolete_entities.append(prev_ent)
            key_path, key_entity = key
            log_rm[key_path].append(key_entity)
    Entity.objects.bulk_update(obsolete_entities, ["obsolete", "date_obsoleted"])

    mod_fields = [
        "string",
        "comment",
        "source",
        "group_comment",
        "resource_comment",
        "context",
    ]
    mod_entities: list[Entity] = []
    added_entities: list[Entity] = []
    log_mod: dict[str, list[str]] = defaultdict(list)
    log_add: dict[str, list[str]] = defaultdict(list)
    for key, next_ent in next_entities.items():
        key_path, key_entity = key
        if key in prev_and_next:
            mod_ent = entity_update(prev_entities[key], next_ent, mod_fields)
            if mod_ent is not None:
                mod_entities.append(mod_ent)
                log_mod[key_path].append(key_entity)
        elif key in next_not_prev:
            added_entities.append(next_ent)
            log_add[key_path].append(key_entity)
    Entity.objects.bulk_update(mod_entities, mod_fields)

    # FIXME: Entity order should be updated on insertion
    # https://github.com/mozilla/pontoon/issues/2115
    added_entities = Entity.objects.bulk_create(added_entities)
    add_count = len(added_entities)

    if log_rm or log_add or log_mod:
        for path in sorted(list(log_rm.keys() | log_add.keys() | log_mod.keys())):
            for desc, log_data in (
                ("Obsolete", log_rm),
                ("Changed", log_mod),
                ("New", log_add),
            ):
                ls = log_data.get(path, None)
                if ls:
                    scope = f"[{project.slug}:{path}]"
                    names = ", ".join(ls).replace("\n", "¶")
                    log.info(f"{scope} {desc} entities ({len(ls)}): {names}")
    return add_count, set(res.path for res in changed_resources)


def add_resources(
    project: Project,
    updates: dict[str, list[VCSTranslation]],
    changed_paths: set[str],
    now: datetime,
) -> tuple[int, set[str]]:
    added_resources = [
        Resource(project=project, path=db_path, format=get_path_format(db_path))
        for db_path, translations in updates.items()
        if translations and db_path not in changed_paths
    ]
    if not added_resources:
        return 0, set()

    added_resources = Resource.objects.bulk_create(added_resources)
    ordered_resources = project.resources.order_by("path")
    for idx, r in enumerate(ordered_resources):
        r.order = idx
    Resource.objects.bulk_update(ordered_resources, ["order"])

    added_entities = Entity.objects.bulk_create(
        (
            entity_from_source(resource, now, idx, tx)
            for resource in added_resources
            for idx, tx in enumerate(updates[resource.path])
        )
    )

    ent_count = len(added_entities)
    added_paths = {ar.path for ar in added_resources}
    log.info(
        f"[{project.slug}] New source files with {ent_count} entities: {', '.join(added_paths)}"
    )
    return ent_count, added_paths


def update_translated_resources(
    project: Project,
    locale_map: dict[str, Locale],
    paths: L10nConfigPaths | L10nDiscoverPaths,
) -> None:
    prev_tr_keys: set[tuple[int, int]] = set(
        (tr["resource_id"], tr["locale_id"])
        for tr in TranslatedResource.objects.filter(resource__project=project)
        .values("resource_id", "locale_id")
        .iterator()
    )
    add_tr: list[TranslatedResource] = []
    for resource in Resource.objects.filter(project=project).iterator():
        _, locales = paths.target(resource.path)
        for lc in locales:
            locale = locale_map.get(lc, None)
            if is_translated_resource(paths, resource, locale):
                assert locale is not None
                key = (resource.pk, locale.pk)
                if key in prev_tr_keys:
                    prev_tr_keys.remove(key)
                else:
                    add_tr.append(TranslatedResource(resource=resource, locale=locale))
    if add_tr:
        add_tr = TranslatedResource.objects.bulk_create(add_tr)
        add_by_res: dict[str, list[str]] = defaultdict(list)
        for tr in add_tr:
            add_by_res[tr.resource.path].append(tr.locale.code)
        for res_path, locale_codes in add_by_res.items():
            locale_codes.sort()
            log.info(
                f"[{project.slug}:{res_path}] Added for translation in: {', '.join(locale_codes)}"
            )
    if prev_tr_keys:
        del_tr_q = Q()
        for resource_id, locale_id in prev_tr_keys:
            del_tr_q |= Q(resource_id=resource_id, locale_id=locale_id)
        _, del_dict = TranslatedResource.objects.filter(del_tr_q).delete()
        del_count = del_dict.get("base.translatedresource", 0)
        str_tr = "translated resource" if del_count == 1 else "translated resources"
        log.info(f"[{project.slug}] Removed {del_count} {str_tr}")


def is_translated_resource(
    paths: L10nConfigPaths | L10nDiscoverPaths,
    resource: Resource,
    locale: Locale | None,
) -> bool:
    if locale is None:
        return False

    if resource.format == "po":
        # For gettext, only create TranslatedResource
        # if the resource exists for the locale.
        target, _ = paths.target(resource.path)
        if target is None:
            return False
        target_path = paths.format_target_path(target, locale.code)
        return isfile(target_path)
    return True


def entity_from_source(
    resource: Resource, now: datetime, idx: int, tx: VCSTranslation
) -> Entity:
    comments = getattr(tx, "comments", None)
    group_comments = getattr(tx, "group_comments", None)
    resource_comments = getattr(tx, "resource_comments", None)
    return Entity(
        string=tx.source_string,
        key=tx.key,
        comment="\n".join(comments) if comments else "",
        order=tx.order or idx,
        source=tx.source,
        resource=resource,
        date_created=now,
        group_comment="\n".join(group_comments) if group_comments else "",
        resource_comment="\n".join(resource_comments) if resource_comments else "",
        context=tx.context,
    )


def entity_update(
    current: Entity, update_from: Entity, fields: list[str]
) -> Optional[Entity]:
    updated = False
    for field in fields:
        value = getattr(update_from, field)
        if getattr(current, field) != value:
            setattr(current, field, value)
            updated = True
    return current if updated else None


def get_db_path(paths: L10nConfigPaths | L10nDiscoverPaths, file_path: str) -> str:
    rel_path = relpath(file_path, paths.ref_root)
    return (
        rel_path[:-1]
        if isinstance(paths, L10nDiscoverPaths) and rel_path.endswith(".pot")
        else rel_path
    )


def get_path_format(path: str) -> str:
    _, extension = splitext(path)
    path_format = extension[1:].lower()

    # Special case: pot files are considered the po format
    if path_format == "pot":
        return "po"
    elif path_format == "xlf":
        return "xliff"
    else:
        return path_format
