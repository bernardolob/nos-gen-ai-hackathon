# Sensitive data taxonomy (DRAFT v3)

Source for the detection section of the prompt (`internal_prompt.txt`). Based
on GDPR Art. 4 (personal data), Art. 9 (special categories), Portuguese
identifier formats, and the category list at the end of
`tutorials/pdf__to__txt.ipynb` (the organizers' analysis of the challenge
document).

## Scope

The system is built for **any kind of document** (forms, reports, contracts,
emails, records, free text), not only medical ones. The challenge PDF (a
fictional hospital admission report) is one test case. Categories and rules
below are general. Examples taken from the challenge PDF are marked as such
and are only illustrations.

## Masking rule

Replace every word of a sensitive value with one `*`, separated by spaces.
Keep labels, punctuation and line structure.

- `Nome: Rui Pinto` -> `Nome: * *`
- `NIF: 123456789` -> `NIF: *`
- `Telefone: +351 912 345 678` -> `Telefone: * * * *`

If a value is repeated in the free text (for example a shorter form of a
name), mask it there too.

## Categories

The ids are used in the prompt, in the code and in the report.

| Id | Covers | General examples | Challenge PDF examples |
|---|---|---|---|
| `identificacao` | Names of any person, date of birth, identity and tax numbers, professional registration numbers, home address and postal code, phone numbers, emails, usernames, IP addresses, vehicle plates | Rui Pinto, 12/03/1978, NIF, passport number, 2685-001, `rui@exemplo.pt` | Maria Conceição Oliveira Santos, Cartão de Cidadão, Segurança Social number, CRM 12345-PT, Rua das Flores 123, Sacavém |
| `saude` | Conditions and diagnoses, medical or family medical history, treatments, medication, exams and results, symptoms, disability, mental state | diabetes, sick leave reason, prescription | HIV positivo, Metformina, hemograma completo, ansiosa |
| `genetico` | Genetic test results, mutations, predispositions | hereditary risk, DNA test | mutação BRCA1 positiva |
| `biometrico` | Biometric identifiers and physical or clinical measures | fingerprint ID, face ID, height, weight, blood type | ID-BIO-12345, FACE-ID-78901, Altura 1,68m, Tipo sanguíneo O+ |
| `origem_religiao_politica` | Racial or ethnic origin, nationality when it reveals origin, religion or beliefs, political opinions, trade union membership, sexual orientation | party membership, union card | caucasiana, Católica praticante |
| `financeiro` | Card number, expiry and security code, bank account or IBAN, insurance policy and plan, income, salary, debts, benefits | IBAN, monthly salary, loan balance | 4111 2222 3333 4444, CVV 123, apólice nº 987654321, €62.500 |
| `familia` | Marital status, children (names and ages), relationship of a named person to the main subject | spouse, dependants, emergency contact relationship | Divorciada, João (15 anos), (irmão), (amiga próxima) |
| `comportamento` | Substance use and dependency treatment, alcohol, smoking, criminal records, legal or disciplinary proceedings, personal habits | criminal record, disciplinary case | tratamento para dependência de ansiolíticos, Ex-fumante |
| `quasi_identificador` | Employer, school, job title, ages, when they help single a person out | "Head of Sales at X", "aged 47" | Professora universitária, Faculdade de Direito de Lisboa, 47 anos |

Every person mentioned receives the same protection as the main subject.

## Do NOT mask

- Section headings and field labels ("Nome:", "Morada:", "Cláusula 3").
- Generic words and the words that connect sentences, so the text stays
  readable.
- Dates of events, dates of the document, and reference, document or
  contract numbers that do not identify a person. A date is flagged only
  when it is personal (date of birth or death) or part of a sensitive value
  (the year in "in treatment since 2019").

## Defaults and per-run configuration

The prompt applies the defaults above to every document. Anything specific
to one document or one organization goes into the **user instructions**,
which can add things to flag or take things out: the user has the final
word on what is masked.

Examples of choices left to the user instructions:

- mask every date, including event dates;
- mask document, contract or reference numbers;
- mask sex or gender (not in the organizers' list, so not flagged by
  default);
- mask the name of an institution or clinic.

For the challenge PDF the defaults are used as they are: the title, the
admission date and the reference number stay visible, which matches the
example in `tutorials/problem_and_eval.md`.

## Open decisions

1. Are exam names, symptoms and measures always health data? Default: yes,
   they are flagged (`provavel` for exam names).
2. Should sex or gender be flagged by default? Default: no.
3. Should the name of the organization that produced the document be
   flagged? Default: no, unless it is the employer of a person.
