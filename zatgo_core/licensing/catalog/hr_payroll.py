"""HR and payroll: hrms (Employee and its setup masters are ERPNext's). Unavailable on a site without hrms."""

from zatgo_core.licensing.registry import MASTER, TRANSACTION, Module, dt, feature

MODULE = Module(id="hr_payroll", label="HR and Payroll", category="Business", order=80, icon="hr",
                source_app="hrms",
                description="Employees, attendance, leave, payroll and expense claims (Frappe HR).")

FEATURES = [
    feature(
        "hr_payroll.employee", "Employees",
        doctypes=[dt("Employee", MASTER), dt("Designation", MASTER), dt("Employee Grade", MASTER)],
        reports=["Employee Information", "Employee Birthday", "Employee Analytics", "Employee Exits"],
        pages=["organizational-chart"],
        workspaces=["HR Setup", "Tenure"],
        api_prefixes=["zatgo_core.api.v1.hr."],
        source_app="hrms",
    ),
    feature(
        "hr_payroll.attendance", "Attendance and shifts",
        doctypes=[dt("Attendance", TRANSACTION), dt("Employee Checkin", MASTER), dt("Shift Type", MASTER),
                  dt("Shift Assignment", TRANSACTION)],
        reports=["Monthly Attendance Sheet", "Shift Attendance", "Employees working on a holiday"],
        workspaces=["Shift & Attendance"],
        requires={"hr_payroll.employee": ["read"]},
        source_app="hrms",
    ),
    feature(
        "hr_payroll.leave", "Leave",
        doctypes=[dt("Leave Application", TRANSACTION), dt("Leave Type", MASTER),
                  dt("Leave Allocation", TRANSACTION), dt("Leave Policy", TRANSACTION)],
        reports=["Employee Leave Balance", "Employee Leave Balance Summary", "Leave Ledger"],
        workspaces=["Leaves"],
        requires={"hr_payroll.employee": ["read"]},
        source_app="hrms",
    ),
    feature(
        "hr_payroll.payroll", "Payroll",
        doctypes=[dt("Salary Structure", TRANSACTION), dt("Salary Structure Assignment", TRANSACTION),
                  dt("Salary Component", MASTER), dt("Salary Slip", TRANSACTION), dt("Payroll Entry", TRANSACTION)],
        reports=["Salary Register", "Bank Remittance", "Salary Payments Based On Payment Mode",
                 "Employee CTC Break-up"],
        workspaces=["Payroll", "Tax & Benefits"],
        requires={"hr_payroll.employee": ["read"]},
        source_app="hrms",
    ),
    feature(
        "hr_payroll.expenses", "Expense claims and advances",
        doctypes=[dt("Expense Claim", TRANSACTION), dt("Employee Advance", TRANSACTION)],
        reports=["Unpaid Expense Claim", "Employee Advance Summary"],
        workspaces=["Expenses"],
        requires={"hr_payroll.employee": ["read"]},
        source_app="hrms",
    ),
]
