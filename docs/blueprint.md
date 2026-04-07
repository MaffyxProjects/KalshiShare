# Referral Draft Assistant Blueprint

## Architecture Diagram

```text
Reddit PRAW Adapter
    -> Opportunity Normalizer
    -> Compliance Parser
    -> Candidate Scorer
    -> Gemini Decision Engine
    -> SQLite (lead_tracker, events, errors, visibility_checks, system_state)
    -> Flask Dashboard
    -> Discord Webhook Alerts
    -> Manual Publish Helper
    -> Optional Anonymous Visibility Check
```

## Step-By-Step Logic Flowchart

```text
Start
  -> Load .env settings and ensure local directories exist
  -> Initialize SQLite schema and runtime logger
  -> Check kill switch in system_state
     -> If enabled, log and stop
  -> For each configured source adapter
     -> Fetch candidates from official/publicly permitted sources
     -> Normalize each candidate into canonical opportunity fields
     -> Skip duplicates using dedupe_key
     -> Fetch rules context for the candidate's community
     -> Parse rules context
        -> If rules explicitly deny referrals, store blocked record
        -> If rules are ambiguous, store blocked record
        -> If rules explicitly allow referrals, continue
     -> Score candidate using keyword, freshness, and engagement signals
     -> Enforce daily candidate and draft caps
     -> Send allowed candidate to Gemini with structured JSON requirements
        -> If Gemini returns invalid JSON, log error and alert
        -> If Gemini marks ineligible, store blocked-by-model record
        -> If Gemini marks eligible, queue for manual review
     -> Notify Discord for high-confidence drafts
  -> Operator opens localhost dashboard
     -> Reviews draft, disclosure, compliance evidence, and source thread
     -> Manually posts outside the app
     -> Pastes public URL back into dashboard
     -> Run anonymous visibility check
        -> Store result and alert on failures
End
```

## Pseudo-Code

### `run_scheduler()`

```text
load settings
initialize logger and database
if kill_switch.enabled:
    log warning
    exit

for adapter in adapters:
    candidates = adapter.fetch_candidates()
    for candidate in candidates:
        if daily candidate cap reached:
            stop loop

        opportunity = adapter.normalize(candidate)
        if database.lead_exists(opportunity.dedupe_key):
            continue

        rules_context = adapter.fetch_rules_context(candidate)
        compliance = compliance_parser.evaluate(rules_context)
        score = scorer.score(opportunity)
        increment candidates counter

        if compliance not allowed:
            decision = blocked decision
            status = blocked_by_compliance
        else if daily draft cap reached:
            decision = deferred decision
            status = deferred_by_cap
        else:
            decision = gemini_service.decide(opportunity, compliance)
            status = queued_for_manual_review if decision.eligible else blocked_by_model
            increment drafts counter if queued

        save draft record to lead_tracker
        log event
        if queued and confidence >= threshold:
            send discord webhook alert
```

### `reddit_adapter.fetch_candidates()`

```text
create PRAW client from local credentials
for each configured subreddit:
    iterate hot(limit=settings.reddit_hot_limit)
    iterate new(limit=settings.reddit_new_limit)
    skip duplicate submission ids
    return RedditCandidate objects
```

### `compliance_parser.evaluate(context)`

```text
split sidebar, rules, and sticky text into lines
search allow patterns
search deny patterns
capture lines mentioning referral, affiliate, promo, or signup terms

if any deny pattern matches:
    return blocked evidence
if any allow pattern matches:
    return allowed evidence
return ambiguous evidence blocked by default
```

### `gemini_decide(opportunity, evidence)`

```text
if compliance is not allowed:
    return ineligible decision immediately

build JSON prompt payload with:
    opportunity data
    compliance evidence
    persona instructions
    token requirements for referral link and disclosure

call Gemini in JSON mode
parse response text as JSON
validate required keys and types
clamp confidence to 0.0-1.0
return standardized GeminiDecision object
```

### `manual_publish_helper(record)`

```text
take model draft text
replace {{referral_link}} with configured referral URL
replace {{disclosure_line}} with standard disclosure
ensure disclosure line exists when required
return rendered text and source-thread URL for the operator
```

### `verify_visibility(public_url, expected_snippet)`

```text
perform anonymous GET request with no authenticated session
if request fails or returns error status:
    mark inconclusive
else if expected snippet exists in response:
    mark visible
else if removal markers exist:
    mark not_visible
else:
    mark inconclusive
store visibility result and alert if not_visible
```

### `dashboard_routes/views`

```text
Overview:
    show daily counts, total leads, kill-switch state, persona chart, recent events
Inbox:
    list queued drafts with compliance evidence and prepared copy
Draft Review:
    record manual posting confirmation and run visibility checks
Logs:
    show log tail plus recent events and errors
Exports & Controls:
    export lead_tracker to CSV, toggle kill switch, run scheduler once
```

## Operational Notes

- The system is local-only and does not auto-post anywhere.
- Future source adapters should be added only for official APIs or operator-supplied public URLs.
- Ambiguous moderation rules always block draft generation.
- Disclosure guidance is preserved end to end through Gemini tokens and manual-review rendering.
- A lightweight local launcher can sit in front of the dashboard so operators can initialize the database, run the scheduler, and start the web UI from one desktop window.
