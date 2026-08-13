# Browser automation boundary v0.4

Status: **adapter boundary implemented; engine integration not bundled**.

Browser automation is a separate subsystem from `http_get` and
`http_request`. It requires a real browser engine for JavaScript, DOM,
viewport, navigator, and browser-cookie behavior. The reference package now
defines `BrowserProfile`, `BrowserPage`, `BrowserAdapter`, and `browser_open`
as the adapter contract. No HTTP fallback is allowed to impersonate a browser.

The first supported adapter engines are reserved as `chromium`, `firefox`, and
`webkit`. No engine dependency is installed with the core interpreter. Calling
the boundary without an adapter produces an explicit
`BrowserAutomationUnavailable` error.

Future Separan source APIs remain experimental and will be capability-gated.
The Python boundary exists now so engine adapters can be developed and tested
without coupling them to the HTTP client.
