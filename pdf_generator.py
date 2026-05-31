from fpdf import FPDF

# The exact dummy text we need for the RAG pipeline
policy_text = """Welcome to the Team!

1. Work Hours & Location
At our company, we believe in a healthy work-life balance. Our standard work hours are from 10:00 AM to 6:00 PM, Monday through Friday. We operate on a hybrid work model. Employees attached to the Bengaluru office are expected to be in the office on Tuesdays and Thursdays, while Mondays, Wednesdays, and Fridays are designated as remote work-from-home days. Flexible hours are permitted as long as you are online during our core collaboration hours of 11:00 AM to 3:00 PM IST.

2. Core Benefits
We are proud to offer a comprehensive suite of core benefits to all full-time employees:
- Health & Wellness: Premium family health insurance covering medical, dental, and vision.
- Paid Time Off (PTO): 21 days of paid annual leave, plus 10 national/regional public holidays. 
- Learning & Development: A dedicated annual stipend of 100,000 INR for courses, certifications, and conferences.
- Home Office Setup: A one-time allowance of 50,000 INR to purchase ergonomic furniture and home office equipment.
- Fitness Stipend: A monthly reimbursement for gym memberships or wellness apps.

3. The Onboarding Process
We want your transition into the company to be as smooth as possible. Your onboarding process will look like this:
- Day 1: IT equipment (MacBook Pro, monitor, and accessories) will be delivered to your home. You will attend a virtual orientation with the HR team to set up your accounts and payroll.
- Week 1: You will be assigned a Company Buddy who will guide you through our internal tools, codebases, and team culture. You will primarily focus on shadowing and reading documentation.
- First 30 Days: You will work with your engineering manager to draft your 30-60-90 day success plan, focusing on your first minor code deployments.

4. Code of Conduct & Culture
We prioritize a culture of radical candor, empathy, and continuous learning. Discrimination, harassment, or toxic behavior of any kind will result in immediate termination. We celebrate diverse backgrounds and encourage everyone to bring their authentic selves to work."""

# Initialize the PDF engine
pdf = FPDF()
pdf.add_page()

# Add Title
pdf.set_font("Arial", 'B', 16)
pdf.cell(200, 10, txt="Company Policies & Employee Handbook", ln=True, align='C')
pdf.ln(10)

# Add Body Text
pdf.set_font("Arial", size=11)
pdf.multi_cell(0, 6, txt=policy_text)

# Export directly to your project folder
pdf.output("company_policies.pdf")
print("✅ Successfully created 'company_policies.pdf' in your current directory!")