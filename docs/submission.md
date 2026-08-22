# Docket — JunctionX Korea 2026 (Upstage Track)

## Punchline (EN)

Drop in any travel document — hotels, flights, tickets, receipts — and Docket turns them into a living itinerary that schedules, reminds, flags conflicts, and guards your refund deadlines.

## Description (EN, markdown)

# Docket — your trip, run by your documents

## Problem

A long trip is buried in documents. Two weeks abroad easily means 20+ bookings — hotels, flights, trains, museum tickets, tours, rental cars — scattered across emails, PDFs, and camera-roll screenshots, in different languages and layouts. So travelers:

- miss check-in windows and timed entry slots,
- find out at the gate that a voucher needed **on-site exchange**,
- lose money because a **cancellation deadline** silently passed,
- book overlapping slots or physically impossible transfers,
- fumble through their photo album hunting for the right QR code.

Planning apps (Triple, Google Travel) help you *dream up* an itinerary but ignore the documents that actually define the trip. Email parsers (TripIt) only read tidy airline confirmation emails — not a scanned PDF from a local tour operator or a photographed paper receipt.

## Our solution

**Docket is a Document Agent for travelers: upload any travel document, and the trip organizes itself.** The documents *are* the itinerary — and the itinerary itself is just another document the agent keeps up to date.

Target users: long-trip, multi-city travelers who juggle dozens of bookings without a travel agency.

## How it works — Upstage Studio Agent pipeline

Every uploaded file (email / PDF / photo) flows through one agent workflow built on Upstage Studio:

1. **Parse** — structures messy real-world documents: scanned vouchers, tables, stamps, mixed-language receipts.
2. **Classify** — detects the document type: hotel / flight / train / attraction ticket / rental car / tour / receipt.
3. **Extract** — pulls the fields that matter per type: dates & times, venue, party size, booking reference, QR/barcode, price, cancellation deadline, entry conditions.
4. **Instruct** — judges conditions and writes plain-language guidance: *Is this booking confirmed or pending? Does it need on-site exchange? Is the refund window still open?* Fine print becomes one-line warnings ("no re-entry", "passport required").
5. **Act — REST API + Webhooks** — the agent then *does the work*: registers calendar events, schedules reminders, inserts the booking into the trip timeline, logs the expense, and files the QR code into the ticket wallet.

## What Docket does

- 📅 **Auto-calendar** — entry dates/times become calendar events with smart reminders
- 🎫 **QR/barcode wallet** — codes extracted and stored per booking; one tap at the gate
- ⚠️ **Conflict detection** — overlapping bookings and too-tight transfers get flagged
- 💸 **Refund guard** — cancellation/refund deadlines tracked and warned before they expire
- ✅ **Condition checks** — confirmation status, exchange-required vouchers, entry rules
- ✍️ **Prompt-native planning** — ask the agent to reshuffle or recommend ("we're too tired for the museum — what fits nearby?"); it edits the plan like any other document
- 📨 **Change-request drafts** — rebooking/cancellation emails auto-drafted from the extracted booking data
- 🧹 **Housekeeping** — expired tickets auto-archived; all spending summarized per trip

## Demo scenario

1. **Before the trip** — the user dumps booking PDFs and screenshots; the itinerary builds itself and two conflicts are flagged instantly.
2. **Travel day** — opening the app initializes the view to the current location: what's next, the right QR code, and today's warnings.
3. **Mid-trip** — pay for an attraction, snap the receipt; the expense is logged and the ticket joins today's timeline.
4. **Document map** — tap any pin on the map and the underlying document appears; a side panel lists every document at a glance.

## Why it's different

TripIt parses tidy airline emails. Triple plans without documents. Docket unifies both around the hardest part — **real, messy documents** — and goes past *understanding* them to **getting the work done**: scheduled, reminded, guarded, and refunded. That is exactly what a Document Agent should be.

**Built with:** Upstage Studio Agent (Parse · Classify · Extract · Instruct) + REST API & Webhooks for calendar, reminders, and itinerary sync.
