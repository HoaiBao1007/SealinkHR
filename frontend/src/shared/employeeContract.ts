export const EMPLOYEE_CONTRACT_OPTIONS = [
  { value: 'APPRENTICESHIP', label: 'Hợp đồng học việc' },
  { value: 'PROBATION', label: 'Hợp đồng thử việc' },
  { value: 'OFFICIAL', label: 'Hợp đồng chính thức' },
  { value: 'FIXED_TERM_1', label: 'Hợp đồng lần 1' },
  { value: 'FIXED_TERM_2', label: 'Hợp đồng lần 2' },
  { value: 'INDEFINITE', label: 'Hợp đồng vô thời hạn' },
] as const

export const isFixedTermEmployeeContract = (contractType?: string | null) =>
  contractType === 'FIXED_TERM_1' || contractType === 'FIXED_TERM_2'
