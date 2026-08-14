export type EmployeeType = 'PROBATION' | 'INTERN' | 'FULLTIME';

export interface SalaryTaxBracket {
  up_to: number | null;
  rate: number;
  deduction: number;
}

export interface SalaryPolicy {
  id?: number;
  version_code?: string;
  name?: string;
  effective_from?: string;
  common_minimum_wage: number;
  regional_minimum_wage_i: number;
  regional_minimum_wage_ii: number;
  regional_minimum_wage_iii: number;
  regional_minimum_wage_iv: number;
  default_region: string;
  social_health_salary_cap: number;
  unemployment_cap_multiplier: number;
  social_employee_rate: number;
  health_employee_rate: number;
  unemployment_employee_rate: number;
  social_employer_rate: number;
  health_employer_rate: number;
  unemployment_employer_rate: number;
  union_fund_employer_rate: number;
  union_employee_rate: number;
  union_employee_cap: number;
  personal_deduction: number;
  dependent_deduction: number;
  probation_withholding_rate: number;
  probation_withholding_threshold: number;
  pit_brackets: SalaryTaxBracket[];
}

export const DEFAULT_SALARY_POLICY: SalaryPolicy = {
  common_minimum_wage: 2_530_000,
  regional_minimum_wage_i: 5_310_000,
  regional_minimum_wage_ii: 4_730_000,
  regional_minimum_wage_iii: 4_140_000,
  regional_minimum_wage_iv: 3_700_000,
  default_region: 'I', social_health_salary_cap: 50_600_000, unemployment_cap_multiplier: 20,
  social_employee_rate: 0.08, health_employee_rate: 0.015, unemployment_employee_rate: 0.01,
  social_employer_rate: 0.175, health_employer_rate: 0.03, unemployment_employer_rate: 0.01,
  union_fund_employer_rate: 0.02, union_employee_rate: 0.005, union_employee_cap: 234_000,
  personal_deduction: 15_500_000, dependent_deduction: 6_200_000,
  probation_withholding_rate: 0.1, probation_withholding_threshold: 2_000_000,
  pit_brackets: [
    { up_to: 10_000_000, rate: 0.05, deduction: 0 },
    { up_to: 30_000_000, rate: 0.1, deduction: 500_000 },
    { up_to: 60_000_000, rate: 0.2, deduction: 3_500_000 },
    { up_to: 100_000_000, rate: 0.3, deduction: 9_500_000 },
    { up_to: null, rate: 0.35, deduction: 14_500_000 },
  ],
};

export interface EmployeeSalaryInput {
  type: EmployeeType;
  contract_salary: number;
  actual_working_days: number;
  standard_working_days: number;
  
  // Raw inputs
  meal_allowance_free?: number;
  meal_allowance_tax?: number;
  phone_allowance_free?: number;
  trans_allowance_tax?: number;
  perf_allowance_tax?: number;
  other_income?: number;
  
  // Backward compatibility keys
  taxable_meal?: number;
  taxable_transport?: number;
  performance_allowance?: number;
  other_allowance?: number;

  bonus: number;
  bonus_14?: number;
  dependents_count: number;
  total_allowances?: number;
  union_fee?: number;
  other_deductions: number;
  pit_refund: number;
  advance_payment: number;
}

export interface SalaryCalculationResult {
  actual_salary: number;
  meal_allowance_free: number;
  meal_allowance_tax: number;
  phone_allowance_free: number;
  trans_allowance_tax: number;
  taxable_income: number;
  assessable_income: number;
  ins_salary: number;
  social_emp: number;
  health_emp: number;
  unemp_emp: number;
  total_ins_emp: number;
  
  // Employer portions
  social_comp: number;
  health_comp: number;
  unemp_comp: number;
  union_fund_comp: number;
  total_ins_comp: number;

  pit_tax: number;
  union_fee: number;
  net_salary: number;
  total_transfer: number;
  final_transfer: number;
}

/**
 * Calculates salary, deductions, taxes and transfer amount for an employee
 * based on the 05/2026 Sealink salary spreadsheet specifications.
 */
export function cake_salary(employee: EmployeeSalaryInput, salaryPolicy: SalaryPolicy = DEFAULT_SALARY_POLICY): SalaryCalculationResult {
  // ── Hằng số Giảm trừ gia cảnh (Cập nhật theo Excel Kế toán trưởng Sealink)
  // const BASE_MAX = 46800000;  // Reserved for future salary cap calculations
  const policy = { ...DEFAULT_SALARY_POLICY, ...salaryPolicy };
  const DEDUCT_SELF = policy.personal_deduction;
  const DEDUCT_DEP = policy.dependent_deduction;
  const STANDARD_DAYS = employee.standard_working_days || 22;

  // 1. Lương thực tế (Col G) & Pro-rated Allowances
  const actual_salary = employee.actual_working_days <= 0
    ? 0
    : employee.actual_working_days >= STANDARD_DAYS
      ? employee.contract_salary
      : (employee.contract_salary / STANDARD_DAYS) * employee.actual_working_days;

  const ratio = Math.min(1.0, employee.actual_working_days / STANDARD_DAYS);

  const mealFree = employee.actual_working_days <= 0
    ? 0
    : Math.round((employee.meal_allowance_free ?? 0) * ratio);

  const mealTax = employee.actual_working_days <= 0
    ? 0
    : Math.round((employee.meal_allowance_tax ?? employee.taxable_meal ?? 0) * ratio);

  const phoneFree = employee.actual_working_days <= 0
    ? 0
    : Math.round((employee.phone_allowance_free ?? 0) * ratio);

  const transTax = employee.actual_working_days <= 0
    ? 0
    : Math.round((employee.trans_allowance_tax ?? employee.taxable_transport ?? 0) * ratio);

  const perfTax = employee.perf_allowance_tax ?? employee.performance_allowance ?? 0;
  const otherInc = employee.other_income ?? employee.other_allowance ?? 0;
  const bonus = employee.bonus ?? 0;
  const bonus_14 = employee.bonus_14 ?? 0;

  // 2. Tổng thu nhập chịu thuế (Col 26)
  const taxable_income =
    actual_salary +
    mealTax +
    transTax +
    perfTax +
    otherInc +
    bonus +
    bonus_14;

  let ins_salary = 0;
  let social_emp = 0;
  let health_emp = 0;
  let unemp_emp = 0;
  let total_ins_emp = 0;
  
  let social_comp = 0;
  let health_comp = 0;
  let unemp_comp = 0;
  let union_fund_comp = 0;
  let total_ins_comp = 0;
  
  let assessable_income = 0;
  let pit_tax = 0;
  let union_fee = 0;

  if ((employee.type === 'PROBATION' || employee.type === 'INTERN') || employee.actual_working_days <= 0) {
    // Khối B Thử việc hoặc Nhân viên chưa tính lương (ngày công = 0)
    // Bảo hiểm = 0
    assessable_income = taxable_income;
    if ((employee.type === 'PROBATION' || employee.type === 'INTERN') && actual_salary > 0) {
      pit_tax = taxable_income >= policy.probation_withholding_threshold
        ? Math.round(taxable_income * policy.probation_withholding_rate)
        : 0;
    } else {
      pit_tax = 0;
    }
    union_fee = 0;
  } else if (employee.type === 'FULLTIME') {
    // Khối A Chính thức (Lương đóng BHXH là không giới hạn)
    ins_salary = Math.min(employee.contract_salary, policy.social_health_salary_cap || employee.contract_salary);
    
    // special BHTN capping for employee & employer (calculated on contract_salary + other_allowance)
    const sum_contract_other = employee.contract_salary + otherInc;
    const regionalMinimum = policy.default_region === 'II'
      ? policy.regional_minimum_wage_ii
      : policy.default_region === 'III'
        ? policy.regional_minimum_wage_iii
        : policy.default_region === 'IV'
          ? policy.regional_minimum_wage_iv
          : policy.regional_minimum_wage_i;
    const unemploymentCap = regionalMinimum * policy.unemployment_cap_multiplier;
    if (sum_contract_other > unemploymentCap) {
      unemp_emp = Math.round(unemploymentCap * policy.unemployment_employee_rate);
    } else {
      unemp_emp = Math.round(sum_contract_other * policy.unemployment_employee_rate);
    }
    
    // Employee insurance (8%, 1.5%, 1%)
    social_emp = Math.round(ins_salary * policy.social_employee_rate);
    health_emp = Math.round(ins_salary * policy.health_employee_rate);
    total_ins_emp = social_emp + health_emp + unemp_emp;

    // Employer insurance (17.5%, 3%, 1%) - Không bao gồm 2% kinh phí công đoàn trong BH bắt buộc
    social_comp = Math.round(ins_salary * policy.social_employer_rate);
    health_comp = Math.round(ins_salary * policy.health_employer_rate);
    unemp_comp = Math.round(
      Math.min(sum_contract_other, unemploymentCap) * policy.unemployment_employer_rate,
    );
    total_ins_comp = social_comp + health_comp + unemp_comp;

    // Kinh phí công đoàn 2%
    union_fund_comp = Math.round(ins_salary * policy.union_fund_employer_rate);

    // Thu nhập tính thuế (Col AA) = Max(0, taxable_income - BH_NLĐ - 15,500,000 - NPT*6,200,000)
    assessable_income = Math.max(
      0,
      taxable_income - total_ins_emp - DEDUCT_SELF - (employee.dependents_count * DEDUCT_DEP)
    );

    // Tính thuế TNCN Lũy tiến theo thang thuế Excel
    const ai = assessable_income;
    let pit = 0;
    const bracket = policy.pit_brackets.find((item) => item.up_to === null || ai <= item.up_to)
      ?? DEFAULT_SALARY_POLICY.pit_brackets[DEFAULT_SALARY_POLICY.pit_brackets.length - 1];
    pit = ai * bracket.rate - bracket.deduction;
    pit_tax = Math.round(Math.max(0, pit));
    
    // Union fee trích nộp NLĐ: Khối chính thức trích 0.5% tính trên Lương nộp BHXH, tối đa 234,000 VND
    union_fee = employee.union_fee !== undefined 
      ? employee.union_fee 
      : Math.round(Math.min(ins_salary * policy.union_employee_rate, policy.union_employee_cap));
  }

  // 3. Lương thực nhận NET
  const total_allowances_all = mealFree + mealTax + phoneFree + transTax + perfTax + otherInc + bonus + bonus_14;

  const net_salary = Math.round(
    actual_salary +
    total_allowances_all -
    total_ins_emp -
    pit_tax
  );

  // 4. Tổng thực chuyển (Col AG) = net_salary + pit_refund - union_fee - other_deductions
  //    Kết quả luôn >= 0 (không âm)
  const total_transfer = Math.max(
    0,
    Math.round(
      net_salary
      + (employee.pit_refund    ?? 0)
      - union_fee
      - (employee.other_deductions ?? 0)
    )
  );
  const final_transfer = Math.max(0, Math.round(total_transfer - (employee.advance_payment ?? 0)));

  return {
    actual_salary,
    meal_allowance_free: mealFree,
    meal_allowance_tax: mealTax,
    phone_allowance_free: phoneFree,
    trans_allowance_tax: transTax,
    taxable_income,
    assessable_income,
    ins_salary,
    social_emp,
    health_emp,
    unemp_emp,
    total_ins_emp,
    social_comp,
    health_comp,
    unemp_comp,
    union_fund_comp,
    total_ins_comp,
    pit_tax,
    union_fee,
    net_salary,
    total_transfer,
    final_transfer,
  };
}
