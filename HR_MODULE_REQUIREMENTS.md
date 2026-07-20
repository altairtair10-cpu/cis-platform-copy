# HR / Кадры Module — Requirements from the HR officer interview

**Source:** ~40-min voice recording (RU), transcribed via TurboScribe in two parts
(full 0–30 min + "trimmed" continuation covering the tail). Coverage is essentially
complete. This document is my interpretation — please have the HR officer read the
"Needs her confirmation" items at the bottom, since a few phrases were ambiguous in
transcription.

**Bottom line on scope:** this is a full *кадровое делопроизводство* (HR records)
module, not a tweak. But the hard part — multi-stage approval routes, signatory /
approvers / recipients, registration, print — **already exists** in the documents
module and is reused, not rebuilt.

---

## A. The core mental model — why everything starts with «Приём»

She was emphatic and repeated this several times: **you cannot issue any order
(приказ) for an employee until that employee has been "accepted"/hired into the
system.** Hiring (приём) is the anchor. Every later order (командировка, отпуск,
etc.) attaches to that already-created employee and feeds their card.

> "чтобы человеку сделать приказ, мы его должны принять… сперва все его стадии
> приёма, потом его стадии приказов."

So the module's spine is: **Приём → employee exists → all other приказы → each feeds
the employee's Единая карточка.**

---

## B. Order categories — Приказы split into "directions"

Orders are grouped into categories she must pick from:

- **По личному составу (ЛС)** — anything touching the person and their money:
  приём (hire), увольнение (termination), отпуск (leave), материальная помощь
  (financial aid), дисциплинарное взыскание (disciplinary action).
  *"Всё, что касается денег его — это по личному составу."*
- **По производству / производственные** — operational: командировки (business
  trips), привлечение к работе в выходные (calling staff in on days off), etc.

She wants to choose the order type from a categorized list — same idea as the
Виды документов picker we just curated on the Требование form.

---

## C. Order types she named (non-exhaustive — she'll provide the full list later)

Приём · Увольнение · Отпуск · Материальная помощь · Дисциплинарное взыскание ·
Командировка (several sub-types) · Привлечение к работе в выходной ·
Совмещение · Премирование · Назначение ответственного · Аттестация · Адаптация.
Related командировка documents: **Отчёт о командировке**, **Продление**, **Отзыв**.

---

## D. Bilingual requirement (hard rule)

**Every order must exist in Russian AND Kazakh.** Position titles, department,
and names all need a Kazakh version (names sometimes transliterated, e.g. "Ралий
Райбек"). *"Все приказы у нас должны быть на двух языках."* This means order forms
need paired RU/KZ fields (surname, position, department, etc.).

---

## E. Приём (hire) order — fields she showed

- Фамилия / ФИО (RU + KZ)
- Должность (position) — RU + KZ
- Структура / подразделение (department/unit the person is hired into)
- Вид приёма (hire type, e.g. «Приём на работу»)
- Дата приёма (hire date) / Выход на работу (start date, e.g. "20 числа")
- Период договора (contract period: from date → to year), Номер договора + дата
- Испытательный срок (probation, e.g. 3 месяца)
- Основание (grounds/basis)
- **Attachments**: scanned заявление (application) with signature must always be
  attached ("оригинал должен быть всегда"); an approver can click through
  ("провалиться") to view it.
- **Auto-linked documents** that should pull automatically from the employee:
  Трудовой договор (employment contract), Договор материальной ответственности
  (liability contract), Согласие на обработку данных (data-processing consent).
  *"Чтобы все данные тянулись за собой."*

---

## F. Командировка (business trip) order — fields she showed

- ФИО (RU + KZ), Должность (RU + KZ)
- **Основание** = references an incoming служебная записка by number (e.g. №534),
  which auto-pulls its data (see section G)
- Даты: from → to (e.g. 20th–26th)
- **Количество дней** = auto-calculated, but counted **straight through — holidays
  are NOT skipped** ("не смотреть на праздник"; 20→27 inclusive = 8 days)
- **Вид транспорта** — selectable and **multiple/mixed** (самолёт, автобус, поезд,
  спецтехника…); she must be able to add several and add her own
- **Маршрут** — origin city → destination / месторождение→месторождение;
  destination should auto-fill after a dash to avoid retyping
- **Цель командировки** (purpose, free text, e.g. «погрузка пропанта»)
- NOT needed on creation: «количество дней продления» (extension days)

---

## G. Служебная записка → Приказ chaining (this is central)

She cannot invent an order herself; an order must be *triggered* by an incoming
memo. Flow she described:

1. A manager (e.g. Женибек) raises a **служебная записка** ("send my warehouse
   lead on a business trip").
2. That memo runs **its own approval route** (согласующие → подписывающий).
3. Once signed, it lands **in her inbox** electronically as an "внутренний
   документ" — *this is exactly the internal-docs flow we already built.*
4. She opens it and **issues the приказ**, with the memo attached as **основание**
   (auto-linked by number; or, if the sender has no account, they email a scan and
   she uploads it).

So: **приказ.основание → link to a Document (служебная записка).** We already have
`in_reply_to_id` on Document — this is the same relationship.

---

## H. Route roles — the multi-signature structure

Per order:

- **Подписывающий** (signatory) — e.g. General Director (Рустем Жумагалевич / Бекишев)
- **Согласующие** (approvers, ordered/parallel route) — "выбрать маршрут"
- **Получатели** (recipients) — for ЛС orders, **бухгалтерия must be auto-added**
- **Список ознакомляющихся** (acknowledgement list) — who must be familiarized with
  the signed order: **the employee himself; if he has no account, his supervisor.**

The first three already exist in our documents engine (we just added Получатели to
the Требование form). **"Ознакомляющиеся" is the one genuinely new role** — an
acknowledgement step distinct from execution.

---

## I. Registration & journal — MANUAL, with back-dating (legal requirement)

This was one of her biggest points and a real pain today:

- After the director signs, **she registers** the order.
- Registration is **manual**: she types the number herself with a category prefix
  (e.g. «ЛС-128», «К-…» for командировка) and **sets the date manually**.
- **Back-dating is required by law.** The order's legal date must be the effective
  date (e.g. the 17th), NOT the date approval finished (e.g. the 20th). Kazakh HR
  cannot register an order dated later than its effective date. Today Documentolog
  stamps the approval date automatically and she has to manually rework the Word
  file to fix it — huge time sink.
- She keeps a **журнал** (register) of every order: **number, date, employee** —
  currently a manual Excel. She wants this journal **inside the system**, showing
  her **unregistered orders** waiting to be registered.
- She wants a **предпросмотр** (preview) before signing, and the ability to
  **доработать** (rework) if she spots a mistake before sending to signature.

---

## J. Output & printing rules

- **Word output, not PDF** — because she needs to edit (mainly the date). PDF is
  the single worst part of the current tool for her. *"В Word, потому что я его не
  могу исправить."*
- **Печать (stamp/seal) must appear** on the printout.
- **QR-code / electronic signature must show on the printout**, so a printed copy
  is valid without her re-collecting a wet signature ("это тройная работа"). She
  confirmed this was already requested/started.
- **Remove per-approver timestamps** from the order: Documentolog prints the exact
  date+time each person approved; she does NOT want that — just "согласован"
  status, no time, because she controls the legal date manually (see I).
- Every signed order is **printed and physically filed** regardless — a hard HR rule.

---

## K. Единая карточка сотрудника (unified employee card) — the centerpiece

Every order feeds a per-employee card that accumulates their whole history:

- Static: ФИО, должность, подразделение, руководитель, дата приёма, стаж (tenure),
  график/вахта, текущий статус
- History pulled from orders: months on командировка, months on отпуск, отпуск
  taken vs. entitled (e.g. 10 of 24 → 14 remaining), premии, аттестации, adaptation
- *"Чтобы на этого человека целая карточка тянулась."* Mirrors how she does it in 1C.
- **Access control:** the card is NOT visible to everyone — only a defined list
  (she named: herself, General Director, Chief Accountant). By contrast, служебные
  записки and заявления are shared/общее пользование.

---

## L. Вахта / schedule & Отпуск balance

- Schedule formats: office **5/2 ("502")** and **вахта** rotations — 14/14, 15/15,
  28/28. Needs a selector/checkbox and should be regulatable per employee, shown on
  the card. *"Чтобы указывалось 502 или вахта… чтобы она регулировалась."*
- **Отпуск balance** tracked per employee (entitled 24, taken, remainder) — connects
  to the existing PTO section.

---

## M. Admin-manageable order types

She wants to add a **new order type herself** via a "+" without always asking the
devs. *"Чтобы я могла… один приказ создать."* → order types must be **reference
data in the DB / admin panel**, not hardcoded. (Aligns with the admin-panel item
already on the roadmap.)

---

## N. Inbox urgency indicators

In her Documentolog inbox, un-executed orders show **black**, urgent/"burning" ones
show **red** ("горит, надо сегодня"), executed ones differ. She wants this
priority coloring in her inbox.

---

## O. 1C integration — FUTURE, not now

Employee data + ID (удостоверение) + bank details live in **1C**. She'd like the
system to read from 1C, but the dev (Женибек) already told her it's expensive/slow
(API cost ~$20). Verdict: **defer** (matches the roadmap's Phase 3). For now she's
fine entering data manually and would love at least the card to hold it.

---

## What already exists that we reuse (so this is assembly, not greenfield)

| She needs | Already built | Reuse |
|---|---|---|
| Multi-stage approval route (согласующие → подписывающий) | `DocumentApproval`, `_build_route`, stepper | Direct |
| Recipients (получатели) | `DocumentRecipient` + the Получатели section we just added | Direct |
| Служебка → приказ основание link | `Document.in_reply_to_id` | Direct |
| Registration concept | `registered_at`, статус «Регистрация» | Extend to manual number/date |
| Print / letterhead | `print_internal.html` (СЗ format) | Template per order type |
| Categorized type picker | Виды документов picker (patch 0008) | Pattern reuse |
| Attachments + click-through | `DocumentAttachment` | Direct |

## What is genuinely new (the real build)

1. **Приказ** as a first-class HR document with **bilingual (RU/KZ) fields** and
   category (ЛС / производство).
2. **Employee onboarding (Приём)** as the anchor that creates the employee record.
3. **Единая карточка сотрудника** — aggregation view + **restricted access list**.
4. **Manual registration journal** with **number entry + back-dating** + an
   "unregistered orders" queue.
5. **Список ознакомляющихся** — new acknowledgement role/step.
6. **Word (.docx) output** with печать + QR — new export path (PDF today).
7. **Командировка** specifics: multi-transport, straight-count days, route auto-fill.
8. **Вахта/schedule + отпуск balance** on the employee record.
9. **Admin-managed order types** (reference data).
10. **Inbox urgency coloring.**

---

## Suggested phasing (each = one reviewable patch, builds on the last)

- **Phase 1 — Приказ foundation.** HR-order model (category, bilingual fields,
  основание link), reusing the existing route/approval/recipients engine; one order
  type end-to-end (Приём or Командировка) as the template.
- **Phase 2 — Manual registration + журнал.** Manual number/date, back-dating,
  unregistered-orders queue, preview-before-sign.
- **Phase 3 — Единая карточка сотрудника.** Aggregation + restricted access.
- **Phase 4 — Word output** with печать + QR; remove approver timestamps.
- **Phase 5 — Ознакомляющиеся, вахта/отпуск balance, inbox coloring, admin order
  types.**
- **Later — 1C integration** (deferred).

---

## Needs her confirmation (transcription ambiguities)

1. "Заявление **с конверсией**" — I read this as the scanned application *with a
   signature/виза*. Correct term?
2. "**502**" = office 5-days-on / 2-off schedule — confirm.
3. Full list of order **types** and their category (ЛС vs производство) — she said
   she'll provide; needed for the picker.
4. Exact **number format** per category (e.g. «ЛС-128», «К-045/2026») — confirm the
   prefix + numbering scheme so registration matches her Excel journal.
5. Who exactly is on the **card access list** (she named herself, GD, Chief
   Accountant — is that the whole list?).
6. Should **бухгалтерия auto-add as recipient** on *all* ЛС orders, or only some?
