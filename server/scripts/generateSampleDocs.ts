/**
 * Generates synthetic (non-PII) sample PDFs for LoanReady demos.
 * Run: npx tsx scripts/generateSampleDocs.ts
 *
 * Outputs under server/sample-docs/:
 *   aadhaar_front.pdf, aadhaar_back.pdf, aadhaar_masked.pdf
 *   pan_card.pdf, kyc_form.pdf
 *   salary_slip_YYYY-MM.pdf (also copied as payslip_*)
 *   bank_statement_6months.pdf
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import PDFDocument from 'pdfkit';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '../sample-docs');

const PERSON = {
  name: 'Rahul Sharma',
  fatherName: 'Suresh Sharma',
  dob: '12/03/1994',
  gender: 'Male',
  employeeId: 'TV-4521',
  designation: 'Senior Analyst',
  employer: 'TechVista Solutions Pvt Ltd',
  /** Synthetic last-4 only — never a real Aadhaar */
  aadhaarLast4: '4321',
  /** Synthetic PAN last-4 chars for demo masking */
  panLast4: 'K5L2',
  /** Full synthetic PAN-shaped string (demo only; not a real allotment) */
  panMasked: 'XXXXXK5L2',
  accountMasked: 'XXXXXX4821',
  ifsc: 'HDFC0001234',
  bank: 'HDFC Bank',
  addressLine1: '12 MG Road',
  addressLine2: 'Bengaluru, Karnataka 560001',
  address: '12 MG Road, Bengaluru, KA 560001',
  phoneMasked: 'XXXXXX7890',
  email: 'rahul.demo@example.com',
};

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function generateMonths(): Array<{ key: string; label: string; gross: number; net: number }> {
  const list = [];
  const d = new Date();
  
  // Generate the last 6 months (ending with the current month)
  for (let i = 5; i >= 0; i--) {
    const temp = new Date(d.getFullYear(), d.getMonth() - i, 1);
    const year = temp.getFullYear();
    const monthIndex = temp.getMonth();
    const monthNum = String(monthIndex + 1).padStart(2, '0');
    
    // Gross and Net salary
    const gross = 85000 + (monthIndex - 5) * 1000; // e.g. 80000 to 85000
    const net = Math.round(gross * 0.84); // e.g. ~71400
    
    list.push({
      key: `${year}-${monthNum}`,
      label: `${MONTH_NAMES[monthIndex]} ${year}`,
      gross,
      net
    });
  }
  return list;
}

const MONTHS = generateMonths();

function ensureOut(): void {
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
}

function money(n: number): string {
  return `Rs. ${n.toLocaleString('en-IN')}`;
}

function pipeDoc(
  file: string,
  draw: (doc: PDFKit.PDFDocument) => void
): Promise<string> {
  const doc = new PDFDocument({ size: 'A4', margin: 40 });
  const stream = fs.createWriteStream(file);
  doc.pipe(stream);
  draw(doc);
  doc.end();
  return new Promise((resolve, reject) => {
    stream.on('finish', () => resolve(file));
    stream.on('error', reject);
  });
}

function watermark(doc: PDFKit.PDFDocument, note: string): void {
  doc
    .fontSize(8)
    .font('Helvetica-Oblique')
    .fillColor('#666666')
    .text(note, 40, doc.page.height - 50, {
      align: 'center',
      width: doc.page.width - 80,
    });
  doc.fillColor('#000000');
}

function drawCard(
  doc: PDFKit.PDFDocument,
  x: number,
  y: number,
  w: number,
  h: number,
  title: string,
  accent: string
): void {
  doc.save();
  doc.roundedRect(x, y, w, h, 8).strokeColor('#333333').lineWidth(1.2).stroke();
  doc.rect(x, y, w, 28).fill(accent);
  doc
    .fillColor('#ffffff')
    .font('Helvetica-Bold')
    .fontSize(11)
    .text(title, x + 12, y + 8, { width: w - 24 });
  doc.restore();
  doc.fillColor('#000000');
}

function writeAadhaarFront(): Promise<string> {
  const file = path.join(OUT, 'aadhaar_front.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(14)
      .font('Helvetica-Bold')
      .text('LoanReady — Synthetic Aadhaar (Front)', { align: 'center' });
    doc.moveDown(0.5);

    const x = 80;
    const y = 100;
    const w = 430;
    const h = 260;
    drawCard(doc, x, y, w, h, 'UIDAI  |  AADHAAR  (DEMO)', '#1a5f9e');

    // Photo placeholder
    doc.roundedRect(x + 20, y + 48, 90, 110, 4).stroke();
    doc
      .fontSize(9)
      .fillColor('#888')
      .text('PHOTO', x + 20, y + 95, { width: 90, align: 'center' });
    doc.fillColor('#000');

    doc.font('Helvetica').fontSize(11);
    const tx = x + 130;
    let ty = y + 50;
    doc.font('Helvetica-Bold').text(PERSON.name, tx, ty);
    ty += 22;
    doc.font('Helvetica').text(`DOB: ${PERSON.dob}`, tx, ty);
    ty += 18;
    doc.text(`Gender: ${PERSON.gender}`, tx, ty);
    ty += 28;
    doc.font('Helvetica-Bold').fontSize(14).text('XXXX XXXX 4321', tx, ty);
    ty += 24;
    doc
      .font('Helvetica')
      .fontSize(9)
      .fillColor('#444')
      .text('(Front face — synthetic demo card)', tx, ty);
    doc.fillColor('#000');

    doc
      .fontSize(9)
      .text(
        'VID / Enrolment: DEMO-NOT-REAL  |  Issued for LoanReady hackathon only',
        x + 20,
        y + h - 36,
        { width: w - 40 }
      );

    watermark(
      doc,
      'Synthetic Aadhaar front. Not issued by UIDAI. No real Aadhaar number.'
    );
  });
}

function writeAadhaarBack(): Promise<string> {
  const file = path.join(OUT, 'aadhaar_back.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(14)
      .font('Helvetica-Bold')
      .text('LoanReady — Synthetic Aadhaar (Back)', { align: 'center' });
    doc.moveDown(0.5);

    const x = 80;
    const y = 100;
    const w = 430;
    const h = 260;
    drawCard(doc, x, y, w, h, 'UIDAI  |  AADHAAR BACK  (DEMO)', '#c45c26');

    doc.font('Helvetica-Bold').fontSize(11);
    doc.text('Address', x + 24, y + 48);
    doc.font('Helvetica').fontSize(10);
    doc.text(PERSON.addressLine1, x + 24, y + 70);
    doc.text(PERSON.addressLine2, x + 24, y + 86);
    doc.moveDown();
    doc.text(`S/O: ${PERSON.fatherName}`, x + 24, y + 114);
    doc.text(`Mobile (masked): ${PERSON.phoneMasked}`, x + 24, y + 132);

    doc.font('Helvetica-Bold').fontSize(12);
    doc.text('XXXX XXXX 4321', x + 24, y + 170);
    doc
      .font('Helvetica')
      .fontSize(9)
      .fillColor('#444')
      .text('QR / barcode area (placeholder — not scannable)', x + 24, y + 198);
    doc
      .roundedRect(x + w - 120, y + 160, 90, 70, 4)
      .strokeColor('#999')
      .stroke();
    doc
      .fillColor('#999')
      .fontSize(8)
      .text('QR', x + w - 120, y + 188, { width: 90, align: 'center' });
    doc.fillColor('#000');

    watermark(
      doc,
      'Synthetic Aadhaar back. Not issued by UIDAI. Address is fictional demo data.'
    );
  });
}

function writeAadhaarMasked(): Promise<string> {
  const file = path.join(OUT, 'aadhaar_masked.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(14)
      .font('Helvetica-Bold')
      .text('e-Aadhaar / Masked Aadhaar (Demo)', { align: 'center' });
    doc
      .fontSize(10)
      .font('Helvetica')
      .text('Downloaded-style printout — only last 4 digits visible', {
        align: 'center',
      });
    doc.moveDown();

    doc.font('Helvetica-Bold').fontSize(12).text('Unique Identification Authority of India');
    doc.moveDown(0.5);
    doc.font('Helvetica').fontSize(11);
    doc.text(`Name: ${PERSON.name}`);
    doc.text(`Date of Birth: ${PERSON.dob}`);
    doc.text(`Gender: ${PERSON.gender}`);
    doc.text(`Aadhaar Number: XXXX XXXX ${PERSON.aadhaarLast4}`);
    doc.moveDown(0.5);
    doc.font('Helvetica-Bold').text('Address');
    doc.font('Helvetica');
    doc.text(PERSON.address);
    doc.moveDown();
    doc.text(`Father / Guardian: ${PERSON.fatherName}`);
    doc.moveDown();
    doc
      .fontSize(10)
      .fillColor('#1a5f9e')
      .text(
        'This is a MASKED Aadhaar sample. Full 12-digit number is never shown in LoanReady demos.'
      );
    doc.fillColor('#000');

    watermark(
      doc,
      'Synthetic masked Aadhaar / e-Aadhaar. Not a UIDAI document.'
    );
  });
}

function writePanCard(): Promise<string> {
  const file = path.join(OUT, 'pan_card.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(14)
      .font('Helvetica-Bold')
      .text('LoanReady — Synthetic PAN Card', { align: 'center' });
    doc.moveDown(0.5);

    const x = 100;
    const y = 120;
    const w = 390;
    const h = 220;
    drawCard(doc, x, y, w, h, 'INCOME TAX DEPARTMENT  |  PAN (DEMO)', '#2e5a3c');

    doc.font('Helvetica').fontSize(10);
    doc.text('Permanent Account Number Card', x + 20, y + 44);
    doc.font('Helvetica-Bold').fontSize(18);
    doc.text(PERSON.panMasked, x + 20, y + 70);
    doc.font('Helvetica').fontSize(11);
    doc.text(`Name: ${PERSON.name}`, x + 20, y + 110);
    doc.text(`Father's Name: ${PERSON.fatherName}`, x + 20, y + 130);
    doc.text(`Date of Birth: ${PERSON.dob}`, x + 20, y + 150);
    doc
      .fontSize(9)
      .fillColor('#555')
      .text(
        `Unmasked demo shape ends with …${PERSON.panLast4} (synthetic — not a real PAN)`,
        x + 20,
        y + 180,
        { width: w - 40 }
      );
    doc.fillColor('#000');

    // Also write a plain alias used by demo.ts naming
    watermark(doc, 'Synthetic PAN. Not issued by Income Tax Department.');
  }).then(async (f) => {
    // Keep legacy filename expected by demo UI text
    fs.copyFileSync(f, path.join(OUT, 'pan_rahul.pdf'));
    return f;
  });
}

function writeKycForm(): Promise<string> {
  const file = path.join(OUT, 'kyc_form.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(16)
      .font('Helvetica-Bold')
      .text('LoanReady — KYC Self-Declaration (Demo)', { align: 'center' });
    doc
      .fontSize(10)
      .font('Helvetica')
      .text('Customer identification pack for loan preparation', {
        align: 'center',
      });
    doc.moveDown();

    doc.font('Helvetica-Bold').fontSize(12).text('1. Applicant details');
    doc.font('Helvetica').fontSize(10);
    doc.text(`Full name: ${PERSON.name}`);
    doc.text(`Father's name: ${PERSON.fatherName}`);
    doc.text(`Date of birth: ${PERSON.dob}`);
    doc.text(`Gender: ${PERSON.gender}`);
    doc.text(`Address: ${PERSON.address}`);
    doc.text(`Mobile (masked): ${PERSON.phoneMasked}`);
    doc.text(`Email: ${PERSON.email}`);
    doc.moveDown();

    doc.font('Helvetica-Bold').fontSize(12).text('2. Identity documents (synthetic)');
    doc.font('Helvetica').fontSize(10);
    doc.text(`Aadhaar (masked): XXXX XXXX ${PERSON.aadhaarLast4}`);
    doc.text(`PAN (masked): ${PERSON.panMasked}`);
    doc.text(`Supporting files: aadhaar_front.pdf, aadhaar_back.pdf, aadhaar_masked.pdf, pan_card.pdf`);
    doc.moveDown();

    doc.font('Helvetica-Bold').fontSize(12).text('3. Employment / income');
    doc.font('Helvetica').fontSize(10);
    doc.text(`Employer: ${PERSON.employer}`);
    doc.text(`Employee ID: ${PERSON.employeeId}`);
    doc.text(`Designation: ${PERSON.designation}`);
    doc.text(`Income proof: salary slips ${MONTHS[0].label} – ${MONTHS[5].label} + 6-month bank statement`);
    doc.moveDown();

    doc.font('Helvetica-Bold').fontSize(12).text('4. Bank account');
    doc.font('Helvetica').fontSize(10);
    doc.text(`Bank: ${PERSON.bank}`);
    doc.text(`Account (masked): ${PERSON.accountMasked}`);
    doc.text(`IFSC: ${PERSON.ifsc}`);
    doc.moveDown();

    doc.font('Helvetica-Bold').fontSize(12).text('5. Declaration');
    doc.font('Helvetica').fontSize(10);
    doc.text(
      'I confirm these details are synthetic demo data for LoanReady. This is not a government KYC submission and contains no real PII.'
    );
    doc.moveDown();
    doc.text(`Applicant signature: ${PERSON.name} (demo)`);
    const today = new Date();
    doc.text(`Date: ${String(today.getDate()).padStart(2, '0')}/${String(today.getMonth() + 1).padStart(2, '0')}/${today.getFullYear()}`);

    watermark(doc, 'Synthetic KYC form for LoanReady demos only.');
  });
}

function writeSalarySlip(month: (typeof MONTHS)[number]): Promise<string> {
  const file = path.join(OUT, `salary_slip_${month.key}.pdf`);
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(16)
      .font('Helvetica-Bold')
      .text(PERSON.employer, { align: 'center' });
    doc
      .fontSize(11)
      .font('Helvetica')
      .text('Payslip / Salary Slip (Demo — Synthetic Data)', { align: 'center' });
    doc.moveDown();
    doc.fontSize(12).font('Helvetica-Bold').text(`Salary Slip — ${month.label}`);
    doc.moveDown(0.5);

    doc.font('Helvetica').fontSize(10);
    doc.text(`Employee Name: ${PERSON.name}`);
    doc.text(`Employee ID: ${PERSON.employeeId}`);
    doc.text(`Designation: ${PERSON.designation}`);
    doc.text(`PAN (masked): ${PERSON.panMasked}`);
    doc.text(`Pay Period: ${month.label}`);
    doc.moveDown();

    const basic = Math.round(month.gross * 0.5);
    const hra = Math.round(month.gross * 0.25);
    const special = month.gross - basic - hra;
    const pf = Math.round(month.gross * 0.12);
    const tax = month.gross - month.net - pf;

    doc.font('Helvetica-Bold').text('Earnings');
    doc.font('Helvetica');
    doc.text(`  Basic:           ${money(basic)}`);
    doc.text(`  HRA:             ${money(hra)}`);
    doc.text(`  Special Allow.:  ${money(special)}`);
    doc.text(`  Gross:           ${money(month.gross)}`);
    doc.moveDown(0.5);
    doc.font('Helvetica-Bold').text('Deductions');
    doc.font('Helvetica');
    doc.text(`  Provident Fund:  ${money(pf)}`);
    doc.text(`  Tax / TDS:       ${money(Math.max(tax, 0))}`);
    doc.moveDown(0.5);
    doc.font('Helvetica-Bold').fontSize(12).text(`Net Pay: ${money(month.net)}`);
    doc.moveDown();
    doc
      .fontSize(9)
      .text(
        `Credited to ${PERSON.bank} A/c ${PERSON.accountMasked} (IFSC ${PERSON.ifsc})`
      );

    watermark(doc, 'LoanReady sample payslip. Not a real salary slip. No real PII.');
  }).then((f) => {
    fs.copyFileSync(f, path.join(OUT, `payslip_${month.key}.pdf`));
    return f;
  });
}

function writeBankStatement(): Promise<string> {
  const file = path.join(OUT, 'bank_statement_6months.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(16)
      .font('Helvetica-Bold')
      .text(PERSON.bank, { align: 'center' });
    doc
      .fontSize(11)
      .font('Helvetica')
      .text('Account Statement (Demo — Synthetic Data)', { align: 'center' });
    doc.moveDown();
    doc.fontSize(10);
    doc.text(`Account Holder: ${PERSON.name}`);
    doc.text(`Account No (masked): ${PERSON.accountMasked}`);
    doc.text(`IFSC: ${PERSON.ifsc}`);
    const today = new Date();
    const firstMonthLabel = MONTHS[0].label;
    const lastMonthLabel = MONTHS[5].label;
    
    // Set statement end day to today's date if last month is current month, otherwise 28
    const lastMonthDate = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastMonthInListDate = new Date(parseInt(MONTHS[5].key.split('-')[0]), parseInt(MONTHS[5].key.split('-')[1]) - 1, 1);
    const isLastMonthCurrentMonth = lastMonthDate.getFullYear() === lastMonthInListDate.getFullYear() && 
                                    lastMonthDate.getMonth() === lastMonthInListDate.getMonth();
    const endDay = isLastMonthCurrentMonth ? today.getDate() : 28;

    doc.text(`Address: ${PERSON.address}`);
    doc.text(`Statement Period: 01 ${firstMonthLabel} – ${String(endDay).padStart(2, '0')} ${lastMonthLabel}`);
    doc.moveDown();

    doc
      .font('Helvetica-Bold')
      .text('Date          Description                        Credit/Debit        Balance');
    doc.font('Helvetica').fontSize(9);
    doc.moveDown(0.3);

    let balance = 98000;
    const rows: string[] = [];

    for (const m of MONTHS) {
      const [yearStr, monthStr] = m.key.split('-');
      const year = parseInt(yearStr);
      const monthIndex = parseInt(monthStr) - 1;
      
      const isCurrentMonth = today.getFullYear() === year && today.getMonth() === monthIndex;
      const currentDay = today.getDate();

      // Salary credit (day 5)
      if (!isCurrentMonth || currentDay >= 5) {
        balance += m.net;
        rows.push(
          `05/${monthStr}/${year}   SALARY CREDIT TECHVISTA          +${m.net.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
        );
      }

      // EMI (day 8)
      if (!isCurrentMonth || currentDay >= 8) {
        const emi = 12000;
        balance -= emi;
        rows.push(
          `08/${monthStr}/${year}   EMI AUTODEBIT LOAN XXX4521       -${emi.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
        );
      }

      // Rent (day 12)
      if (!isCurrentMonth || currentDay >= 12) {
        const rent = 18000;
        balance -= rent;
        rows.push(
          `12/${monthStr}/${year}   UPI RENT PAYMENT                -${rent.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
        );
      }

      // Spends (day 20)
      if (!isCurrentMonth || currentDay >= 20) {
        const misc = 8500;
        balance -= misc;
        rows.push(
          `20/${monthStr}/${year}   POS / UPI SPENDS               -${misc.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
        );
      }
    }

    for (const row of rows) {
      doc.text(row);
    }

    doc.moveDown();
    doc.fontSize(10).font('Helvetica-Bold');
    doc.text(`Closing Balance: Rs. ${balance.toLocaleString('en-IN')}`);
    doc.text(
      `Average Monthly Salary Credit: Rs. ${Math.round(MONTHS.reduce((s, m) => s + m.net, 0) / MONTHS.length).toLocaleString('en-IN')}`
    );

    watermark(
      doc,
      'LoanReady sample bank statement. Not a real account. No real account numbers.'
    );
  });
}

function writeEmploymentLetter(): Promise<string> {
  const file = path.join(OUT, 'employment_letter.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(16)
      .font('Helvetica-Bold')
      .fillColor('#1a5f9e')
      .text(PERSON.employer, { align: 'center' });
    doc
      .fontSize(9)
      .font('Helvetica')
      .fillColor('#666666')
      .text('100, Tech Park, Whitefield, Bengaluru - 560066 | contact@techvista.com', { align: 'center' });
    doc.moveDown(2);

    doc.strokeColor('#1a5f9e').lineWidth(1).moveTo(40, 95).lineTo(555, 95).stroke();
    doc.moveDown(1);

    const today = new Date();
    const dateString = `Date: ${String(today.getDate()).padStart(2, '0')} ${MONTH_NAMES[today.getMonth()]} ${today.getFullYear()}`;
    doc
      .fontSize(10)
      .font('Helvetica')
      .fillColor('#000000')
      .text(dateString, { align: 'right' });
    doc.moveDown(1);

    doc
      .fontSize(12)
      .font('Helvetica-Bold')
      .text('TO WHOMSOEVER IT MAY CONCERN', { align: 'center' });
    doc.moveDown(1.5);

    doc
      .fontSize(11)
      .font('Helvetica')
      .lineGap(4)
      .text(
        `This is to certify that Mr. ${PERSON.name} (Employee ID: ${PERSON.employeeId}) is a permanent employee of ${PERSON.employer}. He has been employed with us since June 15, 2023.`
      );
    doc.moveDown(0.5);
    doc.text(
      `He is currently working in the capacity of ${PERSON.designation}. His current gross salary is Rs. 10,20,000 per annum.`
    );
    doc.moveDown(0.5);
    doc.text(
      'During his tenure, we have found him to be diligent, sincere, and hardworking in his duties.'
    );
    doc.moveDown(2);

    doc.text('For TechVista Solutions Pvt Ltd,');
    doc.moveDown(2.5);
    doc.font('Helvetica-Bold').text('Authorized Signatory');
    doc.font('Helvetica').text('Human Resources Department');

    watermark(doc, 'Synthetic Employment Letter for LoanReady demo purposes only.');
  });
}

function writeForm16(): Promise<string> {
  const file = path.join(OUT, 'form_16.pdf');
  return pipeDoc(file, (doc) => {
    const today = new Date();
    doc
      .fontSize(14)
      .font('Helvetica-Bold')
      .text('FORM NO. 16', { align: 'center' });
    doc
      .fontSize(10)
      .font('Helvetica')
      .text('[See rule 31(1)(a)]', { align: 'center' });
    doc
      .fontSize(11)
      .font('Helvetica-Bold')
      .text('Certificate under section 203 of the Income-tax Act, 1961 for tax deducted at source from income under the head "Salaries"', { align: 'center' });
    doc.moveDown(1.5);

    doc.strokeColor('#333333').lineWidth(1);
    doc.rect(40, doc.y, 515, 120).stroke();

    const topY = doc.y;
    doc.fontSize(9).font('Helvetica-Bold').text('Name and address of the Employer', 45, topY + 5);
    doc.font('Helvetica').text(`${PERSON.employer}\nWhitefield, Bengaluru`, 45, topY + 20);

    doc.font('Helvetica-Bold').text('Name and address of the Employee', 300, topY + 5);
    doc.font('Helvetica').text(`${PERSON.name}\n${PERSON.address}`, 300, topY + 20);

    doc.moveTo(40, topY + 60).lineTo(555, topY + 60).stroke();
    doc.moveTo(290, topY).lineTo(290, topY + 120).stroke();

    doc.font('Helvetica-Bold').text('PAN of the Deductor', 45, topY + 65);
    doc.font('Helvetica').text('AABCT1234F', 45, topY + 80);

    doc.font('Helvetica-Bold').text('PAN of the Employee', 300, topY + 65);
    doc.font('Helvetica').text(PERSON.panMasked, 300, topY + 80);

    doc.moveTo(40, topY + 95).lineTo(555, topY + 95).stroke();

    const currentYear = today.getFullYear();
    const fyStartYear = today.getMonth() >= 5 ? currentYear - 1 : currentYear - 2;
    const fyEndYear = fyStartYear + 1;
    const assessmentYearStr = `${fyEndYear}-${String(fyEndYear + 1).slice(-2)}`;
    const fyPeriodStr = `01-Apr-${fyStartYear} to 31-Mar-${fyEndYear}`;

    doc.font('Helvetica-Bold').text('Assessment Year', 45, topY + 100);
    doc.font('Helvetica').text(assessmentYearStr, 45, topY + 110);

    doc.font('Helvetica-Bold').text('Period with Employer', 300, topY + 100);
    doc.font('Helvetica').text(fyPeriodStr, 300, topY + 110);

    doc.y = topY + 130;
    doc.moveDown(1);

    doc.font('Helvetica-Bold').fontSize(11).text('Summary of Amount Paid and Tax Deducted');
    doc.moveDown(0.5);

    doc.fontSize(9).font('Helvetica-Bold');
    doc.text('1. Gross Salary (under section 17):                 Rs. 9,00,000');
    doc.text('2. Total Deductions under Chapter VI-A:            Rs. 1,50,000');
    doc.text('3. Total Taxable Income (1 - 2):                   Rs. 7,50,000');
    doc.text('4. Tax Payable on Total Income:                    Rs. 32,500');
    doc.text('5. Total Tax Deducted at Source (TDS):             Rs. 32,500');
    doc.text('6. Net Tax Payable:                                Rs. 0');
    doc.moveDown(2);

    doc.font('Helvetica').text('I, HR Manager, certify that a sum of Rs. 32,500 has been deducted at source and paid to the credit of the Central Government.');
    doc.moveDown(1.5);
    doc.text('Signature of the Person responsible for withholding tax:');
    doc.moveDown(1);
    doc.font('Helvetica-Bold').text('For TechVista Solutions Pvt Ltd');

    watermark(doc, 'Synthetic Form 16 for LoanReady demo purposes only.');
  });
}

function writeCancelledCheque(): Promise<string> {
  const file = path.join(OUT, 'cancelled_cheque.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(14)
      .font('Helvetica-Bold')
      .text('LoanReady — Synthetic Cancelled Cheque', { align: 'center' });
    doc.moveDown(0.5);

    const x = 50;
    const y = 100;
    const w = 495;
    const h = 200;

    // Draw cheque box
    doc.save();
    doc.roundedRect(x, y, w, h, 4).strokeColor('#006699').lineWidth(1.5).stroke();
    // Background color tint for cheque
    doc.rect(x + 1, y + 1, w - 2, h - 2).fillColor('#f2fafc').fill();
    doc.restore();

    // Bank Details
    doc.fillColor('#006699').font('Helvetica-Bold').fontSize(12).text(PERSON.bank, x + 15, y + 15);
    doc.fillColor('#555555').font('Helvetica').fontSize(8).text(`MG Road Branch, Bengaluru - 560001\nIFSC: ${PERSON.ifsc}`, x + 15, y + 32);

    // Date Box
    doc.strokeColor('#006699').lineWidth(1);
    doc.font('Helvetica').fontSize(8).fillColor('#000').text('DATE', x + w - 120, y + 15);
    for (let i = 0; i < 8; i++) {
      doc.rect(x + w - 90 + (i * 10), y + 12, 10, 12).stroke();
    }

    // Pay line
    doc.fontSize(10).fillColor('#000').text('PAY __________________________________________________________________ OR BEARER', x + 15, y + 65);
    doc.text('RUPEES __________________________________________________________________________', x + 15, y + 95);

    // Box for Amount
    doc.rect(x + w - 110, y + 90, 95, 20).stroke();
    doc.font('Helvetica-Bold').fontSize(11).text('Rs. ', x + w - 105, y + 95);

    // Account Details
    doc.font('Helvetica').fontSize(9).text(`A/C NO.  ${PERSON.accountMasked}`, x + 25, y + 135);
    doc.strokeColor('#333').lineWidth(1).moveTo(x + 25, y + 150).lineTo(x + 150, y + 150).stroke(); // Line for account number underline

    // Name
    doc.font('Helvetica-Bold').fontSize(10).text(PERSON.name, x + w - 160, y + 145, { width: 140, align: 'right' });
    doc.font('Helvetica').fontSize(8).text('Please sign above', x + w - 160, y + 160, { width: 140, align: 'right' });

    // Cheque Number & details at bottom
    doc.font('Helvetica').fontSize(10).text('"012345"  560240002:  001234"  10', x + 120, y + 175, { width: w - 240, align: 'center' });

    // Cancelled watermark diagonally across
    doc.save();
    doc.fontSize(40).font('Helvetica-Bold').fillColor('#cc0000').opacity(0.15);
    // Draw CANCELLED across the middle
    doc.translate(x + 100, y + 120);
    doc.rotate(-15);
    doc.text('CANCELLED', 0, 0);
    doc.restore();

    watermark(doc, 'Synthetic Cancelled Cheque for LoanReady demo purposes only.');
  });
}

function writeUtilityBill(): Promise<string> {
  const file = path.join(OUT, 'utility_bill.pdf');
  return pipeDoc(file, (doc) => {
    doc
      .fontSize(16)
      .font('Helvetica-Bold')
      .fillColor('#e65c00')
      .text('BESCOM', { align: 'center' });
    doc
      .fontSize(10)
      .font('Helvetica')
      .fillColor('#555')
      .text('Bangalore Electricity Supply Company Limited', { align: 'center' });
    doc.moveDown(1);

    doc.strokeColor('#e65c00').lineWidth(2).moveTo(40, doc.y).lineTo(555, doc.y).stroke();
    doc.moveDown(1);

    doc.fillColor('#000').font('Helvetica-Bold').fontSize(11).text('ELECTRICITY BILL');
    doc.moveDown(0.5);

    const startY = doc.y;
    doc.fontSize(9).font('Helvetica-Bold').text('Customer Details', 45, startY);
    doc.font('Helvetica')
      .text(`Name: ${PERSON.name}`, 45, startY + 15)
      .text(`Address: ${PERSON.address}`, 45, startY + 30)
      .text('Account ID: 1982736452', 45, startY + 55);

    const lastMonth = MONTHS[5];
    const [lastYear, lastMo] = lastMonth.key.split('-');
    const lastMonthDate = new Date(parseInt(lastYear), parseInt(lastMo) - 1, 1);
    const nextMonthDate = new Date(lastMonthDate.getFullYear(), lastMonthDate.getMonth() + 1, 1);
    const nextMonthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const nextMonthLabel = `${nextMonthNames[nextMonthDate.getMonth()]}-${nextMonthDate.getFullYear()}`;
    const billDateLabel = `02-${MONTH_NAMES[lastMonthDate.getMonth()].slice(0, 3)}-${lastYear}`;
    const dueDateLabel = `15-${nextMonthLabel}`;

    doc.font('Helvetica-Bold').text('Bill Details', 320, startY);
    doc.font('Helvetica')
      .text(`Bill Date: ${billDateLabel}`, 320, startY + 15)
      .text(`Billing Month: ${lastMonth.label}`, 320, startY + 30)
      .text(`Due Date: ${dueDateLabel}`, 320, startY + 45)
      .text('Meter No: BLR82918', 320, startY + 60);

    doc.y = startY + 80;
    doc.moveDown(1);

    doc.strokeColor('#ccc').lineWidth(1).rect(40, doc.y, 515, 90).stroke();
    const tableY = doc.y;
    doc.fontSize(9).font('Helvetica-Bold')
      .text('Description', 45, tableY + 5)
      .text('Units', 300, tableY + 5)
      .text('Amount (Rs.)', 450, tableY + 5);

    doc.moveTo(40, tableY + 20).lineTo(555, tableY + 20).stroke();

    doc.font('Helvetica')
      .text('Energy Charges (250 units @ Rs. 8.00)', 45, tableY + 25)
      .text('250', 300, tableY + 25)
      .text('2,000.00', 450, tableY + 25)

      .text('Fixed Charges', 45, tableY + 40)
      .text('-', 300, tableY + 40)
      .text('350.00', 450, tableY + 40)

      .text('FPPCA Charges', 45, tableY + 55)
      .text('-', 300, tableY + 55)
      .text('100.00', 450, tableY + 55);

    doc.moveTo(40, tableY + 70).lineTo(555, tableY + 70).stroke();

    doc.font('Helvetica-Bold')
      .text('Net Bill Amount', 45, tableY + 75)
      .text('2,450.00', 450, tableY + 75);

    doc.y = tableY + 100;
    doc.moveDown(2);

    doc.font('Helvetica-Bold').fontSize(10).text('Important Notes:');
    doc.font('Helvetica').fontSize(8)
      .text('1. Please pay the bill on or before the due date to avoid late payment charges.')
      .text('2. Payments can be made online via BESCOM portal or any UPI application.')
      .text('3. This is a synthetic utility bill generated for LoanReady testing purposes.');

    watermark(doc, 'Synthetic Utility Bill for LoanReady demo purposes only.');
  });
}

/** Keep a single combined aadhaar alias for older demo naming */
function writeAadhaarLegacyCopy(): void {
  const src = path.join(OUT, 'aadhaar_masked.pdf');
  const dest = path.join(OUT, 'aadhaar_rahul.pdf');
  if (fs.existsSync(src)) fs.copyFileSync(src, dest);
}

async function main(): Promise<void> {
  ensureOut();
  const files: string[] = [];

  files.push(await writeAadhaarFront());
  files.push(await writeAadhaarBack());
  files.push(await writeAadhaarMasked());
  files.push(await writePanCard());
  files.push(await writeKycForm());

  for (const m of MONTHS) {
    files.push(await writeSalarySlip(m));
  }

  files.push(await writeBankStatement());
  files.push(await writeEmploymentLetter());
  files.push(await writeForm16());
  files.push(await writeCancelledCheque());
  files.push(await writeUtilityBill());
  writeAadhaarLegacyCopy();

  // Refresh short text stubs for quick inspection
  fs.writeFileSync(
    path.join(OUT, 'salary_slip_rahul.txt'),
    [
      'LoanReady Demo — Sample Salary Slip (mock data, not real PII)',
      '',
      `Employee: ${PERSON.name}`,
      `Employer: ${PERSON.employer}`,
      `Pay Period: ${MONTHS[5].label}`,
      `Gross Salary: ${MONTHS[5].gross}`,
      `Net Salary: ${MONTHS[5].net}`,
      `Designation: ${PERSON.designation}`,
      `Employee ID: ${PERSON.employeeId}`,
      '',
      `See salary_slip_${MONTHS[5].key}.pdf / payslip_${MONTHS[5].key}.pdf for the full PDF.`,
      '',
    ].join('\n'),
    'utf8'
  );
  fs.writeFileSync(
    path.join(OUT, 'bank_statement_rahul.txt'),
    [
      'LoanReady Demo — Sample Bank Statement Summary (mock)',
      '',
      `Account Holder: ${PERSON.name}`,
      `Bank: ${PERSON.bank}`,
      `Period: ${MONTHS[0].label} – ${MONTHS[5].label}`,
      'Average Balance: 145000',
      `Monthly Salary Credit: ${MONTHS[5].net}`,
      'EMI Debits: ~12000/month',
      '',
      'See bank_statement_6months.pdf for the full PDF.',
      '',
    ].join('\n'),
    'utf8'
  );

  console.log('Generated synthetic sample docs in', OUT);
  for (const f of files) console.log(' -', path.basename(f));
  console.log(' - aadhaar_rahul.pdf (copy of masked)');
  console.log(' - pan_rahul.pdf (copy of pan_card)');
  console.log(' - payslip_YYYY-MM.pdf (copies of salary slips)');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
