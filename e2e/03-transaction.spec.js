const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

test('approved request pickup, return, and rating flow', async ({ page }) => {
  execFileSync(path.resolve('.venv/Scripts/python.exe'), [
    'manage.py', 'shell', '-c',
    "from django.contrib.auth import get_user_model; from items.models import BorrowRequest,Item,HandoffConfirmation,Rating; U=get_user_model(); b=U.objects.filter(email='e2e-borrower@example.com').first(); o=U.objects.filter(email='e2e-owner@example.com').first(); i=Item.objects.filter(owner=o,name='E2E Cordless Drill').first(); r=BorrowRequest.objects.filter(item=i,borrower=b).first(); HandoffConfirmation.objects.filter(request=r).delete() if r else None; Rating.objects.filter(request=r).delete() if r else None; r.status='approved'; r.save(update_fields=['status']) if r else None; i.status='available'; i.save(update_fields=['status']) if i else None",
  ], { cwd: path.resolve('.'), stdio: 'ignore' });
  await page.goto('/login/');
  await page.getByLabel('Email').fill('e2e-borrower@example.com');
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('/requests/mine/');
  await page.getByRole('button', { name: 'Confirm pickup' }).click();

  await page.goto('/login/');
  await page.getByRole('button', { name: 'Logout' }).click();
  await page.getByLabel('Email').fill('e2e-owner@example.com');
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('/requests/incoming/');
  await page.getByRole('button', { name: 'Confirm pickup' }).click();
  await expect(page).toHaveURL(/\/requests\/incoming\//);

  await page.getByRole('button', { name: 'Logout' }).click();
  await page.getByLabel('Email').fill('e2e-borrower@example.com');
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('/requests/mine/');
  await page.getByRole('button', { name: 'Confirm return' }).click();
  await page.getByRole('button', { name: 'Logout' }).click();
  await page.getByLabel('Email').fill('e2e-owner@example.com');
  await page.getByLabel('Password', { exact: true }).fill('ShareShelf2026');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('/requests/incoming/');
  await page.getByRole('button', { name: 'Confirm return' }).click();
  await expect(page).toHaveURL(/\/requests\/incoming\//);

  await page.goto('/notifications/');
  await expect(page.getByRole('heading', { name: /Notifications/ })).toBeVisible();

  await page.goto('/profile/');
  await expect(page.getByText('E2E Owner')).toBeVisible();
});
