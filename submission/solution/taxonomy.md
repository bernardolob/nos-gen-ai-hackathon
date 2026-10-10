# Sensitive data taxonomy (DRAFT v2)

Source for the detection section of the prompt. The final text must be
pasted into `submission/prompt.txt`. Based on GDPR Art. 4 (personal data),
Art. 9 (special categories), Portuguese identifier formats, and the category
list at the end of `tutorials/pdf__to__txt.ipynb` (the organizers' own
analysis of the document).

Items marked (?) are borderline: the team must decide before the prompt is
frozen.

## Masking rule

Replace every word of a sensitive value with one `*`, separated by spaces.
Keep labels, punctuation and line structure.

- `Nome: Maria Conceição Oliveira Santos` -> `Nome: * * * *`
- `NIF: 097865413` -> `NIF: *`
- `Telefone: +351 912 345 678` -> `Telefone: * * * *`

If a value is repeated in the free text (e.g. "Maria Santos"), mask it
there too.

## 1. Personal identification data (always mask)

| Category | Examples in the document |
|---|---|
| Names of people | Maria Conceição Oliveira Santos, Maria Santos, António Santos, Joana Pereira, Dr. Carlos Mendes |
| Date of birth | 12/03/1978 |
| Identity documents | NIF, Cartão de Cidadão, Número da Segurança Social, CRM 12345-PT |
| Residential address | Rua das Flores, 123, Apt 45, Sacavém, Lisboa |
| Contacts | phone numbers and email addresses of the patient, relatives, friend and doctor |

## 2. Health data (always mask)

| Category | Examples |
|---|---|
| Medical conditions | hipertensão, diabetes tipo 2, HIV positivo, carga viral indetectável |
| Medical history | dores abdominais intensas, diagnosticada há 5 anos |
| Family medical history | cancro da mama (mãe), doença cardíaca (pai e avô paterno) |
| Prescribed medication | antirretrovirais, Metformina, Losartana, Alprazolam, dosages |
| Exams and results | hemograma completo, glicemia em jejum, perfil lipídico, ultrassonografia abdominal |
| Symptoms and mental state | ansiosa, cansaço, fadiga, stress, dificuldade em dormir |

## 3. Genetic data (always mask)

mutação BRCA1 positiva, predisposição ao cancro da mama, exames genéticos.

## 4. Biometric data (always mask)

| Category | Examples |
|---|---|
| Biometric identifiers | ID-BIO-12345, FACE-ID-78901 (impressão digital, reconhecimento facial) |
| Physical and clinical measures | Altura 1,68m, Peso 72kg, Tipo sanguíneo O+, Pressão arterial 145/90 mmHg |

## 5. Racial or ethnic origin, religion, politics, sexual orientation

| Category | Examples |
|---|---|
| Ethnicity | caucasiana |
| Religion | Católica praticante |
| Political opinions or affiliation | none in the PDF, but mask if found |
| Sexual orientation | none in the PDF, but mask if found |

## 6. Financial data (always mask)

| Category | Examples |
|---|---|
| Credit card number, expiry, CVV | 4111 2222 3333 4444, 09/27, 123 |
| Insurance policy and plan | apólice nº 987654321, Plano Premium Saúde Total |
| Income | €62.500 |
| Bank details | IBAN, account numbers if present |

## 7. Family life (always mask)

| Category | Examples |
|---|---|
| Marital status | Divorciada |
| Children: names and ages | João, 15 anos, Ana, 12 anos, Filhos: 2 |
| Relationships to the patient | (irmão), (amiga próxima) |

## 8. Personal behaviours (always mask)

| Category | Examples |
|---|---|
| Substance use history | Tratamento para dependência de ansiolíticos em 2019 |
| Alcohol | consome álcool socialmente (2-3 doses por semana) |
| Smoking | Ex-fumante (parou há 3 anos) |

## 9. Quasi-identifiers (mask when they help single a person out)

| Category | Examples |
|---|---|
| Employer or workplace | Faculdade de Direito de Lisboa |
| Occupation | Professora universitária |
| Age | 47 anos, 52 anos |
| Sex (?) | Feminino |

## 10. Third parties

People other than the patient (relatives, friend, doctor) get the same
protection: mask their names, contacts and any personal or health details.

## 11. Do NOT mask

- Section headings and field labels ("Informações do Paciente:", "Nome:",
  "Telefone:", "Histórico Médico:").
- Generic words with no personal content ("paciente", "consulta",
  "histórico", "relatando").
- Sentence connectors, so the text stays readable.
- The document title ("Relatório de Admissão - Centro Médico Lisboa") and the
  admission date, which the problem statement example leaves visible (?).
- The reference number `ADM-2025-04-15-089` (?): kept visible in the example
  in `tutorials/problem_and_eval.md`.

## 12. Decisions needed from the team

1. Mask the reference number and the admission date? The example in the
   problem statement keeps them, so the default is no.
2. Mask "Sexo: Feminino"? It is not in the organizers' category list, so the
   default is no.
3. Mask the doctor's specialty (Medicina Interna)? Default is no.
4. Mask the exam list and the symptom descriptions? The organizers' list
   covers medical history and results, so the default is yes.

## Caveat

The notebook's sample text is from an older version of the document: it has
sexual orientation, political affiliation and a CPF that the real PDF does not
contain. Always check categories against
`raw_data/document_to_anonymize.pdf`.
