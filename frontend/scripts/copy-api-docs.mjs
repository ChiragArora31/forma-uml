import { copyFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
const destination = new URL('public/api-docs/', root);
await mkdir(destination, { recursive: true });
for (const name of ['swagger-ui-bundle.js', 'swagger-ui.css']) {
  await copyFile(
    fileURLToPath(new URL(`node_modules/swagger-ui-dist/${name}`, root)),
    fileURLToPath(new URL(name, destination)),
  );
}
