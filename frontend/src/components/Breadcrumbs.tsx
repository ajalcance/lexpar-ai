/**
 * File: src/components/Breadcrumbs.tsx
 * Purpose: A lightweight breadcrumb strip for interior pages (anything deeper than the Cases
 *   list). One consistent back-navigation pattern replacing the ad-hoc, differently-worded
 *   "Cancel" / "go to dashboard" / "Back to cases" buttons. Each page passes its own trail so
 *   dynamic labels (a case title, "Scorecard") stay page-owned; the shell renders no data itself.
 * Depends on: react-router-dom (Link)
 * Related: components/AppLayout.tsx (topbar it sits under), pages/* (each supplies its trail)
 */

import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

/** One crumb; omit `to` for the current (non-link) page at the end of the trail. */
export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-6">
      <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <Fragment key={`${item.label}-${index}`}>
              <li>
                {item.to && !isLast ? (
                  <Link to={item.to} className="hover:text-foreground">
                    {item.label}
                  </Link>
                ) : (
                  <span aria-current={isLast ? 'page' : undefined} className="text-foreground">
                    {item.label}
                  </span>
                )}
              </li>
              {!isLast && (
                <li aria-hidden="true">
                  <ChevronRight className="size-3.5" />
                </li>
              )}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
