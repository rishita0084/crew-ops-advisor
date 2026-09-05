import React from 'react';

interface SuggestedQuestionsProps {
  onSelect: (question: string) => void;
  disabled: boolean;
}

const SUGGESTIONS = [
'Captain C-1042 just called in sick for tomorrow. What should I do?',
'Who is on reserve at BLR on 2026-09-15?',
'If I move Captain C-2087 onto P-2291, does anyone breach a duty limit?',
'BLR is closed 08:00-14:00Z on 17 Sep. What is the crew impact?'];


export function SuggestedQuestions({ onSelect, disabled }: SuggestedQuestionsProps) {
  return (
    <div className="mt-4">
      <h2 className="sr-only">Suggested questions</h2>
      <ul className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((question) =>
        <li key={question}>
            <button
            type="button"
            disabled={disabled}
            onClick={() => onSelect(question)}
            className="rounded-full border border-line bg-surface px-4 py-2 text-left text-xs text-fg-muted transition-colors duration-150 ease-out hover:border-line-strong hover:text-fg disabled:text-fg-faint">
            
              {question}
            </button>
          </li>
        )}
      </ul>
    </div>);

}