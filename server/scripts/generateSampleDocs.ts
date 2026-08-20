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

const MONTHS = [
  { key: '2025-08', label: 'August 2025', gross: 82000, net: 69000 },
  { key: '2025-09', label: 'September 2025', gross: 83000, net: 70000 },
  { key: '2025-10', label: 'October 2025', gross: 84000, net: 71000 },
  { key: '2025-11', label: 'November 2025', gross: 84000, net: 71000 },
  { key: '2025-12', label: 'December 2025', gross: 86000, net: 73000 },
  { key: '2026-01', label: 'January 2026', gross: 85000, net: 72000 },
];

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
    doc.text('Income proof: salary slips Aug 2025 – Jan 2026 + 6-month bank statement');
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
    doc.text(`Date: 20/08/2026`);

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
    doc.text(`Address: ${PERSON.address}`);
    doc.text('Statement Period: 01 Aug 2025 – 31 Jan 2026');
    doc.moveDown();

    doc
      .font('Helvetica-Bold')
      .text('Date          Description                        Credit/Debit        Balance');
    doc.font('Helvetica').fontSize(9);
    doc.moveDown(0.3);

    let balance = 98000;
    const rows: string[] = [];

    for (const m of MONTHS) {
      const [, mo] = m.key.split('-');
      const y = m.key.split('-')[0];
      balance += m.net;
      rows.push(
        `05/${mo}/${y}   SALARY CREDIT TECHVISTA          +${m.net.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
      );

      const emi = 12000;
      balance -= emi;
      rows.push(
        `08/${mo}/${y}   EMI AUTODEBIT LOAN XXX4521       -${emi.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
      );

      const rent = 18000;
      balance -= rent;
      rows.push(
        `12/${mo}/${y}   UPI RENT PAYMENT                -${rent.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
      );

      const misc = 8500;
      balance -= misc;
      rows.push(
        `20/${mo}/${y}   POS / UPI SPENDS               -${misc.toLocaleString('en-IN').padStart(10)}   ${balance.toLocaleString('en-IN')}`
      );
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
  writeAadhaarLegacyCopy();

  // Refresh short text stubs for quick inspection
  fs.writeFileSync(
    path.join(OUT, 'salary_slip_rahul.txt'),
    [
      'LoanReady Demo — Sample Salary Slip (mock data, not real PII)',
      '',
      `Employee: ${PERSON.name}`,
      `Employer: ${PERSON.employer}`,
      'Pay Period: January 2026',
      'Gross Salary: 85000',
      'Net Salary: 72000',
      `Designation: ${PERSON.designation}`,
      `Employee ID: ${PERSON.employeeId}`,
      '',
      'See salary_slip_2026-01.pdf / payslip_2026-01.pdf for the full PDF.',
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
      'Period: August 2025 – January 2026',
      'Average Balance: 145000',
      'Monthly Salary Credit: 72000',
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
