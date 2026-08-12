# HTTP server preview

Separan declares routes as named structures rather than anonymous callbacks.

```separan
http_route GET "/user/:id" :user_page
id = request_param("id")
return_http(status = 200, body = "user=" + id)
end_http_route:user_page

http_host(host = "127.0.0.1", port = 8080)
```

The preview supports `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE` routes.
`request_method`, `request_path`, `request_header`, `request_param`,
`request_query`, `request_body`, and `request_cookie` inspect the active request.
`return_http` completes it, `redirect_http` returns an explicit redirect, and
`http_set_cookie` adds a response cookie. A route without either return function
produces status 204; an unmatched route produces 404.

`http_host` is a blocking development server and requires the `host_http`
capability. Allowed bind hosts and ports are controlled independently. The
transport-independent dispatcher exposed by the reference implementation is the
future adapter boundary for serverless and production hosts.

`http_static(url = "/static/", directory = "public")` serves GET and HEAD from a
capability-relative directory. The URL prefix must start and end with `/`.
Directories resolve to `index.html`; directory listings do not exist. URL
decoding, traversal segments, backslashes, absolute paths, symlink escapes, and
missing files cannot escape or disclose the capability root. Explicit routes
take precedence over static mounts.

Request cookies are returned as redacted `secret` values. Response cookie names,
values, paths, and SameSite settings are validated. The preview does not execute
JavaScript and is not a production application server.
