export type CartesianPoint = {
  x: number;
  y: number;
  z: number;
};

/**
 * Convert WGS84-style latitude/longitude to the globe coordinate system.
 * Longitude 0° faces the camera at the initial rotation; east is screen-right.
 */
export function geoToCartesian(latitude: number, longitude: number, radius = 1): CartesianPoint {
  const latitudeRadians = latitude * (Math.PI / 180);
  const longitudeRadians = longitude * (Math.PI / 180);
  const latitudeRadius = Math.cos(latitudeRadians) * radius;

  return {
    x: latitudeRadius * Math.sin(longitudeRadians),
    y: radius * Math.sin(latitudeRadians),
    z: latitudeRadius * Math.cos(longitudeRadians),
  };
}
