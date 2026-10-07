import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir } from 'node:fs/promises';

const screenshotDir = '../docs/screenshots';

test('complete reviewer journey: 14 UML views, revisions, review, source, export, reload', async ({
  page,
}) => {
  await mkdir(screenshotDir, { recursive: true });
  const consoleErrors: string[] = [];
  page.on('pageerror', (error) => consoleErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  await page.screenshot({ path: `${screenshotDir}/welcome.png`, fullPage: true });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  await page.getByRole('button', { name: 'Choose UML diagram types' }).click();
  await page.getByRole('button', { name: 'Select all 14' }).click();
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(14);
  await page.getByRole('button', { name: 'Use 14 views' }).click();
  await page.getByRole('button', { name: 'Open the SEBI case study' }).click();
  await expect(
    page.getByRole('heading', { name: 'SEBI compliance monitor', exact: true }),
  ).toBeVisible();
  const views = page.getByLabel('Select UML view');
  await expect(views.locator('option')).toHaveCount(14);
  for (const option of await views.locator('option').all()) {
    await views.selectOption((await option.getAttribute('value'))!);
    const image = page.getByRole('img', { name: /UML diagram/ });
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
      .toBeTruthy();
  }
  await page.getByLabel('Select UML view').selectOption('component');
  await page.screenshot({ path: `${screenshotDir}/workspace.png`, fullPage: true });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  await page.getByRole('button', { name: 'Add a queue, retries & failure recovery' }).click();
  await page.getByRole('button', { name: 'Send design request' }).click();
  await expect(page.getByLabel('Select revision')).toHaveValue('1');
  await page.getByRole('button', { name: 'Changes', exact: true }).click();
  await expect(page.getByText('Analysis queue', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Require officer approval before publication' }).click();
  await page.getByRole('button', { name: 'Send design request' }).click();
  await expect(page.getByLabel('Select revision')).toHaveValue('2');
  await page.getByRole('button', { name: 'Design notes', exact: true }).click();
  await expect(
    page.getByText('A compliance officer must approve the impact report before publication.', {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Review design', exact: true }).click();
  await page.getByRole('button', { name: 'Rate 4 out of 5' }).click();
  await page
    .getByLabel('What worked? What needs to change?')
    .fill('The separation of ingestion and analysis is useful. Keep officer sign-off explicit.');
  await page.screenshot({ path: `${screenshotDir}/review.png`, fullPage: true });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole('button', { name: 'Save review' }).click();
  await expect(page.getByText(/1 review saved/)).toBeVisible();

  await page.getByRole('button', { name: 'Source', exact: true }).click();
  await page
    .getByLabel('PlantUML source editor')
    .fill('@startuml\nAlice -> Bob: A valid preview\n@enduml');
  await page.getByRole('button', { name: 'Check & preview' }).click();
  await expect(page.getByRole('img', { name: 'Edited preview UML diagram' })).toBeVisible();
  await page.getByLabel('PlantUML source editor').fill('@startuml\nclass {\nbroken\n@enduml');
  await page.getByRole('button', { name: 'Check & preview' }).click();
  await expect(page.getByRole('alert')).toContainText('PlantUML rejected');
  await page.getByLabel('PlantUML source editor').fill('@startuml\n!include /etc/passwd\n@enduml');
  await page.getByRole('button', { name: 'Check & preview' }).click();
  await expect(page.getByRole('alert')).toContainText('disabled');

  const filePromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Export ZIP', exact: true }).click();
  expect((await filePromise).suggestedFilename()).toBe('forma-revision-3.zip');
  await page.reload();
  await page
    .getByRole('button', { name: 'SEBI compliance monitor 3 revisions', exact: true })
    .click();
  await expect(page.getByLabel('Select revision')).toHaveValue('2');
  await expect(page.getByText(/1 review saved/)).toBeVisible();
  await page.getByLabel('Select revision').selectOption('0');
  await page.getByRole('button', { name: 'Design notes', exact: true }).click();
  await expect(page.getByText('Analysis queue', { exact: true })).toHaveCount(0);
  await page.getByLabel('Select revision').selectOption('2');
  await page.getByRole('button', { name: 'Diagram', exact: true }).click();
  await page.getByLabel('Select UML view').selectOption('component');
  await page.getByRole('button', { name: 'Expand canvas' }).click();
  await expect(page.getByRole('button', { name: 'Exit full screen' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Expand canvas' })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('mobile layout, keyboard dialog control, and honest sample-mode errors', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: `${screenshotDir}/mobile.png`, fullPage: true });
  await page.getByRole('button', { name: 'How Forma works' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  if (await page.getByLabel('Generation options').isVisible()) {
    await page.getByLabel('Generation options').click();
    await page.getByRole('button', { name: 'Case study', exact: true }).click();
  }
  await page
    .getByLabel('Describe your software design')
    .fill('Build a bookstore with checkout and payments');
  await page.getByRole('button', { name: 'Send design request' }).click();
  await expect(page.getByRole('alert')).toContainText('Switch to live mode');
  await expect(page.getByLabel('Describe your software design')).toHaveValue(
    'Build a bookstore with checkout and payments',
  );
});

test('API documentation works under the production content security policy', async ({ page }) => {
  test.skip(
    !process.env.FORMA_E2E_URL,
    'Run against the built API server for documentation testing',
  );
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/docs');
  await expect(page.getByRole('heading', { name: /Forma UML API/ })).toBeVisible();
  await expect(page.getByText('/api/generate', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
