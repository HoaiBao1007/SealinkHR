import { SEALINK_BRANCHES } from '../src/components/sealinkBranches.ts';
import { geoToCartesian } from '../src/components/globeCoordinates.ts';

const countriesUrl = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson';
const expectedCountryNames = {
  usa: 'United States of America',
  brazil: 'Brazil',
  uae: 'United Arab Emirates',
  pakistan: 'Pakistan',
  vietnam: 'Vietnam',
};

const pointInRing = ([longitude, latitude], ring) => {
  let inside = false;
  for (let current = 0, previous = ring.length - 1; current < ring.length; previous = current, current += 1) {
    const [currentLongitude, currentLatitude] = ring[current];
    const [previousLongitude, previousLatitude] = ring[previous];
    const crossesLatitude = (currentLatitude > latitude) !== (previousLatitude > latitude);
    const crossingLongitude = ((previousLongitude - currentLongitude) * (latitude - currentLatitude))
      / (previousLatitude - currentLatitude || Number.EPSILON) + currentLongitude;
    if (crossesLatitude && longitude < crossingLongitude) inside = !inside;
  }
  return inside;
};

const pointInPolygon = (point, polygon) => {
  if (!pointInRing(point, polygon[0])) return false;
  return polygon.slice(1).every((hole) => !pointInRing(point, hole));
};

const pointInGeometry = (point, geometry) => {
  if (geometry.type === 'Polygon') return pointInPolygon(point, geometry.coordinates);
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.some((polygon) => pointInPolygon(point, polygon));
  }
  return false;
};

const collection = await fetch(countriesUrl).then((response) => {
  if (!response.ok) throw new Error(`Natural Earth countries HTTP ${response.status}`);
  return response.json();
});

const results = SEALINK_BRANCHES.map((branch) => {
  const expectedCountry = expectedCountryNames[branch.id];
  const feature = collection.features.find((candidate) => candidate.properties?.ADMIN === expectedCountry);
  if (!feature) throw new Error(`Không tìm thấy quốc gia Natural Earth: ${expectedCountry}`);
  const point = [branch.longitude, branch.latitude];
  return {
    branch: branch.label,
    expectedCountry,
    latitude: branch.latitude,
    longitude: branch.longitude,
    insideCountry: pointInGeometry(point, feature.geometry),
  };
});

const failures = results.filter((result) => !result.insideCountry);
const orientation = {
  primeMeridianFacesCamera: geoToCartesian(0, 0).z > 0,
  eastIsScreenRight: geoToCartesian(0, 90).x > 0,
  westIsScreenLeft: geoToCartesian(0, -90).x < 0,
  northIsUp: geoToCartesian(90, 0).y > 0,
};
const orientationFailed = Object.values(orientation).some((value) => !value);
console.log(JSON.stringify({
  result: failures.length || orientationFailed ? 'FAIL' : 'PASS',
  orientation,
  branches: results,
}, null, 2));
if (failures.length || orientationFailed) process.exitCode = 1;
