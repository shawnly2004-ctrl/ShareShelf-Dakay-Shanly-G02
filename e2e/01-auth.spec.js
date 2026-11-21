const { test, expect } = require('@playwright/test');

test('registration, login failure, login success, profile, and logout', async ({ page }) => {
  const suffix = Date.now();
  const email = `e2e-member-${suffix}@example.com`;

  await page.goto('/register/');
  await page.getByLabel('First name').fill('E2E');
  await page.getByLabel('Last name').fill('Member');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Community').selectOption({ index: 1 });
  await page.getByLabel('Address detail').fill('Purok E2E');
  await page.getByLabel('Latitude').fill('10.315699');
  await page.getByLabel('Longitude').fill('123.885436');
  await page.getByLabel('User type').selectOption('both');
  await page.getByLabel('Language pref').selectOption('en');
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByLabel('Confirm password').fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Register' }).click();
  await expect(page).toHaveURL(/\/login\//);

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('WrongPassword1');
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByText('Invalid email or password. Please try again.', { exact: true })).toBeVisible();

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/dashboard\//);

  await page.goto('/profile/');
  await expect(page.getByText('E2E Member')).toBeVisible();
  await page.getByRole('button', { name: 'Logout' }).click();
  await expect(page).toHaveURL(/\/login\//);
});
