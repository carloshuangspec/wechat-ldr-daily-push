# Gemini English love-line API setup

## Goal and scope

Generate a brief English romantic line for the existing WeChat template while keeping the existing static English fallback. This change does not enable a scheduled or manual live WeChat send, alter recipients, or change weather/date behavior.

## Credential boundary

- The key pasted into chat is treated as exposed and must not be used or copied into the repository. Carlos revokes it in Google AI Studio and creates a new key privately.
- Carlos enters the replacement only as the GitHub Actions Secret `GEMINI_API_KEY`. No key value appears in source, documentation, command arguments, URL parameters, tests, or logs.
- The prompt stays generic and omits names, dates, OpenIDs, and other relationship details.

## Approaches and choice

1. Set only the existing `GEMINI_MODEL` variable and add a Secret. This avoids a code change but keeps authentication in a URL query parameter and cannot clearly distinguish a generated line from fallback.
2. Use the `gemini-flash-latest` alias from the example curl. This tracks newer releases, including preview or experimental models, so behavior may change without a repository edit.
3. **Chosen:** keep the current `generateContent` request shape, set the default to Google's stable `gemini-3.8-flash`, put the new key in the `x-goog-api-key` header, and expose a non-secret success/fallback signal in preview. The existing `GEMINI_MODEL` variable can still override the default later.

## Data flow and failure handling

The five existing GitHub Actions message jobs already pass `GEMINI_API_KEY` and `GEMINI_MODEL` to the application. The Gemini module asks for an English line of at most 20 printable ASCII characters; accepted output becomes the existing `love_line` field. For Gemini 3.8 Flash, use `thinkingLevel=low`, allow a bounded 512 output tokens (including hidden reasoning), and remove the obsolete sampling temperature; do not accept a `MAX_TOKENS` truncated candidate. Missing key, HTTP failure, malformed or truncated output, non-ASCII output, or overlong output falls back to one of the existing English lines. A non-secret diagnostic records whether a valid generated line was used, without logging the key, raw error body, or private identifiers.

## Verification

- Mocked tests check the stable default/optional override, request header and absence of URL/query key, low-thinking generation config, a valid generated line, and failure fallbacks. Existing send-gate tests must remain green.
- After the new Secret is saved, run only the existing GitHub Actions `preview` mode for both slots. Confirm safe diagnostics show Gemini generation rather than only `gemini_key_set: true` and inspect the English `love_line` text. The preview jobs do not load WeChat credentials or send a message.
- A successful preview does not establish phone delivery and does not turn on `ENABLE_CN_DAILY` or any US daily live send. Any real send remains a separate, explicit decision.
