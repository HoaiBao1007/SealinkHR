export type BranchOffice = {
  id: string;
  label: string;
  country: string;
  latitude: number;
  longitude: number;
  pulseOffset: number;
  /** Public image shown in the branch hover card. */
  imageUrl?: string;
};

// Representative country coordinates are used until exact office cities are
// confirmed. Update this one file when adding branch images or precise sites.
export const SEALINK_BRANCHES: BranchOffice[] = [
  { id: 'usa', label: 'SEALINK USA', country: 'USA', latitude: 37.0902, longitude: -95.7129, pulseOffset: 0.00, imageUrl: '/branch-offices/usa.jpg' },
  { id: 'brazil', label: 'SEALINK BRAZIL', country: 'Brazil', latitude: -14.2350, longitude: -51.9253, pulseOffset: 0.20, imageUrl: '/branch-offices/brazil.webp' },
  { id: 'uae', label: 'SEALINK UAE', country: 'UAE', latitude: 23.4241, longitude: 53.8478, pulseOffset: 0.40, imageUrl: '/branch-offices/uae.png' },
  { id: 'pakistan', label: 'SEALINK PAKISTAN', country: 'Pakistan', latitude: 30.3753, longitude: 69.3451, pulseOffset: 0.60, imageUrl: '/branch-offices/pakistan.jpg' },
  { id: 'vietnam', label: 'SEALINK VIETNAM', country: 'Viet Nam', latitude: 14.0583, longitude: 108.2772, pulseOffset: 0.80, imageUrl: '/branch-offices/vietnam.jpg' },
];
