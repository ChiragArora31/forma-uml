import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';

async function exposeLiveControls(page: import('@playwright/test').Page) {
  await page.route('**/api/session', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, mode: 'live', model: 'fixture-model' } });
  });
}

async function openSample(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Open the SEBI case study' }).click();
  await expect(
    page.getByRole('heading', { name: 'SEBI compliance monitor', exact: true }),
  ).toBeVisible();
}

test('workspace management preserves drafts, revisions, and reversible archives', async ({
  page,
}) => {
  await openSample(page);
  const draft = 'Add explicit tenancy boundaries to the analysis workspace';
  await page.getByLabel('Describe your software design').fill(draft);
  await expect
    .poll(async () =>
      page.evaluate(() =>
        Object.values(localStorage).some((v) => v.includes('explicit tenancy boundaries')),
      ),
    )
    .toBeTruthy();
  await page.reload();
  await expect(page.getByLabel('Describe your software design')).toHaveValue(draft);
  await expect(
    page.getByRole('heading', { name: 'SEBI compliance monitor', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Design settings' }).click();
  await page.getByLabel('Design name').fill('Compliance design — final review');
  await page.getByRole('button', { name: 'Save name' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Compliance design — final review 1 revision', exact: true }),
  ).toBeVisible();
  await page.getByLabel('Search designs').fill('no match');
  await expect(page.getByText('No designs match “no match”.')).toBeVisible();
  await page.getByRole('button', { name: 'Clear search' }).click();
  await page.getByRole('button', { name: 'Design settings' }).click();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole('button', { name: 'Archive design', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  await page.getByRole('button', { name: 'Undo archive' }).click();
  await expect(
    page.getByRole('heading', { name: 'SEBI compliance monitor', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Describe your software design')).toHaveValue(draft);
  await page.getByRole('button', { name: 'Design settings' }).click();
  await page.getByRole('button', { name: 'Archive design', exact: true }).click();
  await page.getByRole('button', { name: 'Show archived designs' }).click();
  await page
    .getByRole('button', { name: 'Compliance design — final review 1 revision', exact: true })
    .click();
  await expect(page.getByRole('button', { name: 'Send design request' })).toBeDisabled();
  await page.getByRole('button', { name: 'Restore', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Send design request' })).toBeEnabled();
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
});

test('all source exports match the selected preview and failures remain readable', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await openSample(page);
  const canvas = page.getByRole('region', { name: 'Component diagram canvas', exact: true });
  await canvas.focus();
  await page.keyboard.press('ArrowRight');
  await expect(canvas.locator('.diagram-image')).toHaveAttribute('style', /translate\(-40px/);
  await page.getByRole('button', { name: 'Fit diagram to canvas' }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom out', exact: true }).click();
  await page.getByRole('button', { name: 'Reset zoom to 100 percent' }).click();
  await expect(page.getByRole('button', { name: 'Reset zoom to 100 percent' })).toHaveText('100%');
  await page.getByRole('button', { name: 'Source', exact: true }).click();
  const source = '@startuml\nAlice -> Bob: A reviewed preview\n@enduml';
  await page.getByLabel('PlantUML source editor').fill(source);
  await expect(page.getByRole('button', { name: '.svg', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '.png', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Copy', exact: true }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(source);
  const puml = page.waitForEvent('download');
  await page.getByRole('button', { name: '.puml', exact: true }).click();
  const sourceDownload = await puml;
  expect(await readFile((await sourceDownload.path())!, 'utf8')).toBe(source);
  await page.getByRole('button', { name: 'Check & preview' }).click();
  await expect(page.getByRole('img', { name: 'Edited preview UML diagram' })).toBeVisible();
  const svgDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: '.svg', exact: true }).click();
  const svg = await svgDownload;
  expect(svg.suggestedFilename()).toBe('component-preview.svg');
  expect(await readFile((await svg.path())!, 'utf8')).toContain('A reviewed preview');
  const pngDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: '.png', exact: true }).click();
  const png = await pngDownload;
  expect(png.suggestedFilename()).toBe('component-preview.png');
  expect((await readFile((await png.path())!)).subarray(0, 8)).toEqual(
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );
  await page.getByLabel('PlantUML source editor').fill('                    ');
  await page.getByRole('button', { name: 'Check & preview' }).click();
  await expect(page.getByRole('alert')).toContainText('Source must contain');
  await page.getByRole('button', { name: 'Reset to generated source' }).click();
  await expect(page.getByLabel('PlantUML source editor')).not.toHaveValue(source);
  const reportDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download design review brief' }).click();
  const report = await reportDownload;
  expect(await readFile((await report.path())!, 'utf8')).toContain('## Requirements');
  await page.route('**/api/revisions/*/export', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Export service is temporarily unavailable. Your design is safe.',
      }),
    }),
  );
  await page.getByRole('link', { name: 'Export ZIP' }).click();
  await expect(page.getByRole('status')).toContainText('Export service is temporarily unavailable');
});

test('starter briefs, quota mode, selection controls, and cancellation keep user work', async ({
  page,
}) => {
  await exposeLiveControls(page);
  await page.goto('/');
  const input = page.getByLabel('Describe your software design');
  const send = page.getByRole('button', { name: 'Send design request' });
  await expect(input).toBeEnabled();
  await expect(send).toBeDisabled();
  await expect(
    page.getByText('Type your brief above (at least 10 characters) to enable Send.'),
  ).toBeVisible();
  await input.fill('queue');
  await expect(send).toBeDisabled();
  await expect(page.getByText('Add 5 more characters to enable Send.')).toBeVisible();
  await input.fill('Add queues');
  await expect(send).toBeEnabled();
  await input.fill('          ');
  await expect(send).toBeDisabled();
  await page.getByRole('button', { name: /A reliable document pipeline/ }).click();
  await expect(page.getByLabel('Describe your software design')).toHaveValue(
    /document processing platform/,
  );
  await page.getByRole('button', { name: 'Choose UML diagram types' }).click();
  await page.getByRole('button', { name: 'Select all 14' }).click();
  await page.getByRole('button', { name: 'Recommended pair' }).click();
  await page.getByRole('button', { name: 'Use 2 views' }).click();
  const draft = await page.getByLabel('Describe your software design').inputValue();
  await expect
    .poll(async () =>
      page.evaluate(() =>
        Object.values(localStorage).some((v) => v.includes('document processing platform')),
      ),
    )
    .toBeTruthy();
  await page.reload();
  await expect(page.getByLabel('Describe your software design')).toHaveValue(draft);
  let release: () => void = () => undefined;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/generate', async (route) => {
    await blocked;
    await route.abort().catch(() => undefined);
  });
  await page.getByRole('button', { name: 'Send design request' }).click();
  await expect(page.getByRole('button', { name: 'Stop generation' })).toBeVisible();
  await page.getByRole('button', { name: 'Stop generation' }).click();
  release();
  await expect(page.getByRole('button', { name: 'Stop generation' })).not.toBeVisible();
  await expect(page.getByLabel('Describe your software design')).toHaveValue(draft);
  await page.getByLabel('Generation options').click();
  await page.getByRole('button', { name: 'Case study', exact: true }).click();
  await expect(page.getByText('Instant curated examples · no AI quota used')).toBeVisible();
});

test('mobile users can open, start, and manage their saved workspace', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openSample(page);
  await page.getByRole('button', { name: 'Open workspace' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await page.getByRole('button', { name: 'Open workspace' }).click();
  await page.getByLabel('Find a design').fill('SEBI');
  await page.getByRole('button', { name: /SEBI compliance monitor.*1 revision/ }).click();
  await expect(
    page.getByRole('heading', { name: 'SEBI compliance monitor', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Source', exact: true }).click();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.getByRole('button', { name: 'Design settings' }).click();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
});
