import React, { useContext } from 'react';

import type { MachineryTranslation } from '~/api/machinery';
import { Locale } from '~/context/Locale';
import { GenericTranslation } from '~/modules/translation';

import { TranslationMemory } from './source/TranslationMemory';

type Props = {
  sourceString: string;
  translation: MachineryTranslation;
};

type tmEntry = {
  projectName: string;
  projectSlug: string;
  projectDisabled: boolean;
  entities: number[];
};

function ProjectList({ tmEntries }: { tmEntries: tmEntry[] }) {
  const { code } = useContext(Locale);

  if (tmEntries.length === 0) {
    return <TranslationMemory />;
  }

  return (
    <>
      {tmEntries.map((tmEntry) => (
        <li key={tmEntry.projectName}>
          {tmEntry.entities.length > 0 && !tmEntry.projectDisabled ? (
            <a
              className='translation-source'
              href={`/${code}/${tmEntry.projectSlug}/all-resources/?list=${tmEntry.entities.join(',')}`}
              onClick={(e) => e.stopPropagation()}
            >
              <span>{tmEntry.projectName.toUpperCase()}</span>
            </a>
          ) : (
            <span className='translation-source'>
              <span>{tmEntry.projectName.toUpperCase()}</span>
            </span>
          )}
        </li>
      ))}
    </>
  );
}

export function ConcordanceSearch({
  sourceString,
  translation,
}: Props): React.ReactElement {
  const { code, direction, script } = useContext(Locale);
  const tmEntries = translation.tmEntries;

  const title = tmEntries
    ?.reduce((acc, entry) => {
      acc.push(entry.projectName);
      return acc;
    }, [] as string[])
    .join(' • ');

  return (
    <>
      <header>
        <ul className='sources projects' title={title}>
          {tmEntries && <ProjectList tmEntries={tmEntries} />}
        </ul>
      </header>
      <p className='original'>
        <GenericTranslation
          content={translation.original}
          search={sourceString}
        />
      </p>
      <p
        className='suggestion'
        dir={direction}
        data-script={script}
        lang={code}
      >
        <GenericTranslation
          content={translation.translation}
          search={sourceString}
        />
      </p>
    </>
  );
}
