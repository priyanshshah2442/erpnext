# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import re
import unittest

import frappe
from frappe.model.naming import parse_naming_series

from erpnext.accounts.doctype.gl_entry.gl_entry import rename_gle_sle_docs
from erpnext.accounts.doctype.journal_entry.test_journal_entry import make_journal_entry

test_dependencies = ["Company", "Account", "Finance Book"]


class TestGLEntry(unittest.TestCase):
	def test_round_off_entry(self):
		frappe.db.set_value("Company", "_Test Company", "round_off_account", "_Test Write Off - _TC")
		frappe.db.set_value("Company", "_Test Company", "round_off_cost_center", "_Test Cost Center - _TC")

		jv = make_journal_entry(
			"_Test Account Cost for Goods Sold - _TC",
			"_Test Bank - _TC",
			100,
			"_Test Cost Center - _TC",
			submit=False,
		)

		jv.get("accounts")[0].debit = 100.01
		jv.flags.ignore_validate = True
		jv.submit()

		round_off_entry = frappe.db.sql(
			"""select name from `tabGL Entry`
			where voucher_type='Journal Entry' and voucher_no = %s
			and account='_Test Write Off - _TC' and cost_center='_Test Cost Center - _TC'
			and debit = 0 and credit = '.01'""",
			jv.name,
		)

		self.assertTrue(round_off_entry)

	def test_rename_entries(self):
		je = make_journal_entry(
			"_Test Account Cost for Goods Sold - _TC", "_Test Bank - _TC", 100, submit=True
		)
		rename_gle_sle_docs()
		naming_series = parse_naming_series(parts=frappe.get_meta("GL Entry").autoname.split(".")[:-1])

		je = make_journal_entry(
			"_Test Account Cost for Goods Sold - _TC", "_Test Bank - _TC", 100, submit=True
		)

		gl_entries = frappe.get_all(
			"GL Entry",
			fields=["name", "to_rename"],
			filters={"voucher_type": "Journal Entry", "voucher_no": je.name},
			order_by="creation",
		)

		self.assertTrue(all(entry.to_rename == 1 for entry in gl_entries))
		old_naming_series_current_value = frappe.db.sql(
			"SELECT current from tabSeries where name = %s", naming_series
		)[0][0]

		rename_gle_sle_docs()

		new_gl_entries = frappe.get_all(
			"GL Entry",
			fields=["name", "to_rename"],
			filters={"voucher_type": "Journal Entry", "voucher_no": je.name},
			order_by="creation",
		)
		self.assertTrue(all(entry.to_rename == 0 for entry in new_gl_entries))

		self.assertTrue(
			all(new.name != old.name for new, old in zip(gl_entries, new_gl_entries, strict=False))
		)

		new_naming_series_current_value = frappe.db.sql(
			"SELECT current from tabSeries where name = %s", naming_series
		)[0][0]
		self.assertEqual(old_naming_series_current_value + 2, new_naming_series_current_value)

	def test_validate_balance_type(self):
		account1_name = "_Test Finance Books"
		account2_name = "_Test Bank"
		account1 = account1_name + " - _TC"
		account2 = account2_name + " - _TC"

		if not frappe.db.exists("Account", {"account_name": account1_name, "company": "_Test Company"}):
			create_test_account(account1_name)
		else:
			clear_previous_balances(account1)

		make_journal_entry(account1, account2, 1000, submit=True)

		financial_accounting_je = make_journal_entry(account1, account2, -1000, save=False)
		financial_accounting_je.finance_book = "Financial Accounting"
		financial_accounting_je.insert()
		financial_accounting_je.submit()

		tax_accounting_je1 = make_journal_entry(account1, account2, -500, save=False)
		tax_accounting_je1.finance_book = "Tax Accounting"
		tax_accounting_je1.insert()
		tax_accounting_je1.submit()

		tax_accounting_je2 = make_journal_entry(account1, account2, -600, save=False)
		tax_accounting_je2.finance_book = "Tax Accounting"
		tax_accounting_je2.insert()

		self.assertRaisesRegex(
			frappe.ValidationError,
			re.compile(r"^(Balance for Account .* must always be Debit)"),
			tax_accounting_je2.submit,
		)


def create_test_account(account_name):
	account = frappe.new_doc("Account")
	account.update(
		{
			"account_name": account_name,
			"parent_account": "Current Assets",
			"company": "_Test Company",
			"is_group": 0,
			"account_type": "Fixed Asset",
			"account_currency": "INR",
			"balance_must_be": "Debit",
		}
	)
	account.insert()


def clear_previous_balances(account_name):
	gl = frappe.qb.DocType("GL Entry")
	frappe.qb.from_(gl).delete().where(gl.account == account_name).run()
