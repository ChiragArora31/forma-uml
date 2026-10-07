window.addEventListener('DOMContentLoaded', async () => {
  await fetch('/api/session');
  window.SwaggerUIBundle({
    url: '/openapi.json',
    dom_id: '#swagger-ui',
    persistAuthorization: false,
    requestInterceptor: (request) => {
      request.headers['X-Forma-Request'] = '1';
      return request;
    },
  });
});
