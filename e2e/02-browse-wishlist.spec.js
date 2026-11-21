const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

test('browse community items and create a wishlist entry', async ({ page }) => {
  execFileSync(path.resolve('.venv/Scripts/python.exe'), [
    'manage.py', 'shell', '-c',
    "from items.models import Wishlist; from django.contrib.auth import get_user_model; u=get_user_model().objects.filter(email='e2e-borrower@example.com').first(); Wishlist.objects.filter(user=u).delete() if u else None",
  ], { cwd: path.resolve('.'), stdio: 'ignore' });
  await page.goto('/login/');
  await page.getByLabel('Email').fill('e2e-borrower@example.com');
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(/\/dashboard\//);

  await page.goto('/items/browse/');
  await expect(page.getByRole('heading', { name: 'Browse Items' })).toBeVisible();

  await page.goto('/wishlists/');
  await expect(page.getByRole('heading', { name: 'My Wishlist' })).toBeVisible();
  await page.getByLabel('Keyword').fill('cordless drill');
  await page.getByRole('button', { name: 'Add entry' }).click();
  await expect(page.getByText('cordless drill').first()).toBeVisible();
});
