/**
 * File: src/lib/limits.ts
 * Purpose: Form-field length caps for `maxLength` on inputs/textareas — immediate UX so a user
 *   can't type past the limit. Mirror of backend `app/schemas/limits.py` (the real enforcement);
 *   keep the two in sync.
 */

/** Single-line fields (titles, party names, case numbers, citations, person/firm names). */
export const LINE_MAX = 200;

/** Multi-line free-text answers (relief sought, additional case context, jurisdiction blurb). */
export const TEXT_MAX = 1000;
