import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { geoToCartesian } from './globeCoordinates';
import { SEALINK_BRANCHES, type BranchOffice } from './sealinkBranches';

type GeoPosition = [longitude: number, latitude: number];
type GeoPolygon = GeoPosition[][];
type NaturalEarthGeometry =
  | { type: 'Polygon'; coordinates: GeoPolygon }
  | { type: 'MultiPolygon'; coordinates: GeoPolygon[] };
type NaturalEarthCollection = {
  type: 'FeatureCollection';
  features: Array<{ geometry: NaturalEarthGeometry | null }>;
};
type NaturalEarthBoundaryGeometry =
  | { type: 'LineString'; coordinates: GeoPosition[] }
  | { type: 'MultiLineString'; coordinates: GeoPosition[][] };
type NaturalEarthBoundaryCollection = {
  type: 'FeatureCollection';
  features: Array<{ geometry: NaturalEarthBoundaryGeometry | null }>;
};

const NATURAL_EARTH_DATA_VERSION = '20260817';
const NATURAL_EARTH_LAND_URL = `/data/ne_110m_land.geojson?v=${NATURAL_EARTH_DATA_VERSION}`;
const NATURAL_EARTH_BOUNDARIES_URL = `/data/ne_110m_admin_0_boundary_lines_land.geojson?v=${NATURAL_EARTH_DATA_VERSION}`;

export default function Login3DGlobe() {
  const mountRef = useRef<HTMLDivElement>(null);
  const branchTargetRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const branchHoverActiveRef = useRef(false);
  const [hoveredBranch, setHoveredBranch] = useState<BranchOffice | null>(null);
  const [hoverPosition, setHoverPosition] = useState({ x: 16, y: 16 });
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    if (!mountRef.current) return;
    const mount = mountRef.current;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, mount.clientWidth / mount.clientHeight, 0.1, 1000);
    camera.position.z = 11;

    const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1));
    mount.appendChild(renderer.domElement);

    // Bỏ EffectComposer, ShaderPass, FilmPass, FXAAPass để tránh lag/freeze.

    const globeRadius = 4;
    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    // THIẾT LẬP LỚP KHÍ QUYỂN PHÁT SÁNG GLOW ATMOSPHERE (Fresnel effect)
    // Để bật lại, hãy uncomment toàn bộ block dưới đây và dòng globeGroup.add(atmosphere)
    /*
    const atmosphereGeometry = new THREE.SphereGeometry(globeRadius + 0.15, 64, 64);
    const atmosphereMaterial = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        void main() {
          float intensity = pow(0.65 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.5);
          gl_FragColor = vec4(0.2, 0.6, 1.0, 0.7) * intensity;
        }
      `,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true
    });
    const atmosphere = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    // globeGroup.add(atmosphere); // Tạm thời tắt glow orb để giảm độ sáng của quả địa cầu
    */

    // A dark inner sphere gives the point cloud real depth and hides land on
    // the far side instead of allowing continents to overlap through the globe.
    const globeCore = new THREE.Mesh(
      new THREE.SphereGeometry(globeRadius - 0.035, 64, 64),
      new THREE.MeshBasicMaterial({ color: 0x020b1d }),
    );
    globeCore.renderOrder = 0;
    globeGroup.add(globeCore);

    const basePositions: number[] = [];
    const basePointCount = 7000;
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    for (let index = 0; index < basePointCount; index += 1) {
      const normalizedY = 1 - (2 * (index + 0.5)) / basePointCount;
      const radial = Math.sqrt(Math.max(0, 1 - normalizedY * normalizedY));
      const angle = goldenAngle * index;
      basePositions.push(
        Math.cos(angle) * radial * globeRadius,
        normalizedY * globeRadius,
        Math.sin(angle) * radial * globeRadius,
      );
    }
    const baseGeometry = new THREE.BufferGeometry();
    baseGeometry.setAttribute('position', new THREE.Float32BufferAttribute(basePositions, 3));
    const baseMaterial = new THREE.PointsMaterial({
      color: 0x0b2949,
      size: 0.018,
      transparent: true,
      opacity: 0.18,
      depthWrite: false,
    });
    globeGroup.add(new THREE.Points(baseGeometry, baseMaterial));

    const mapAbortController = new AbortController();
    let disposed = false;

    const addNaturalEarthMap = (
      collection: NaturalEarthCollection,
      boundaryCollection: NaturalEarthBoundaryCollection,
    ) => {
      if (disposed) return;

      const polygons: GeoPolygon[] = [];
      for (const feature of collection.features) {
        if (!feature.geometry) continue;
        if (feature.geometry.type === 'Polygon') polygons.push(feature.geometry.coordinates);
        else polygons.push(...feature.geometry.coordinates);
      }

      const coastlineSegments: number[] = [];
      for (const polygon of polygons) {
        const outerRing = polygon[0];
        for (let index = 1; index < outerRing.length; index += 1) {
          const [previousLongitude, previousLatitude] = outerRing[index - 1];
          const [longitude, latitude] = outerRing[index];
          if (Math.abs(longitude - previousLongitude) > 180) continue;
          const previousPoint = geoToCartesian(previousLatitude, previousLongitude, globeRadius + 0.018);
          const point = geoToCartesian(latitude, longitude, globeRadius + 0.018);
          coastlineSegments.push(
            previousPoint.x, previousPoint.y, previousPoint.z,
            point.x, point.y, point.z,
          );
        }
      }
      const coastlineGeometry = new THREE.BufferGeometry();
      coastlineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(coastlineSegments, 3));
      const coastlineMaterial = new THREE.LineBasicMaterial({
        color: 0x5eefff,
        transparent: true,
        opacity: 0.76,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const coastlineLines = new THREE.LineSegments(coastlineGeometry, coastlineMaterial);
      coastlineLines.renderOrder = 2;
      globeGroup.add(coastlineLines);

      const boundarySegments: number[] = [];
      for (const feature of boundaryCollection.features) {
        if (!feature.geometry) continue;
        const lines = feature.geometry.type === 'LineString'
          ? [feature.geometry.coordinates]
          : feature.geometry.coordinates;
        for (const line of lines) {
          for (let index = 1; index < line.length; index += 1) {
            const [previousLongitude, previousLatitude] = line[index - 1];
            const [longitude, latitude] = line[index];
            if (Math.abs(longitude - previousLongitude) > 180) continue;
            const previousPoint = geoToCartesian(previousLatitude, previousLongitude, globeRadius + 0.021);
            const point = geoToCartesian(latitude, longitude, globeRadius + 0.021);
            boundarySegments.push(
              previousPoint.x, previousPoint.y, previousPoint.z,
              point.x, point.y, point.z,
            );
          }
        }
      }
      const boundaryGeometry = new THREE.BufferGeometry();
      boundaryGeometry.setAttribute('position', new THREE.Float32BufferAttribute(boundarySegments, 3));
      const boundaryMaterial = new THREE.LineBasicMaterial({
        color: 0x28c7ed,
        transparent: true,
        opacity: 0.38,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const boundaryLines = new THREE.LineSegments(boundaryGeometry, boundaryMaterial);
      boundaryLines.renderOrder = 2;
      globeGroup.add(boundaryLines);
    };

    const fetchNaturalEarth = async <T,>(url: string): Promise<T> => {
      const response = await fetch(url, { signal: mapAbortController.signal });
      if (!response.ok) throw new Error(`Natural Earth HTTP ${response.status}: ${url}`);
      return response.json() as Promise<T>;
    };

    void Promise.all([
      fetchNaturalEarth<NaturalEarthCollection>(NATURAL_EARTH_LAND_URL),
      fetchNaturalEarth<NaturalEarthBoundaryCollection>(NATURAL_EARTH_BOUNDARIES_URL),
    ])
      .then(([land, boundaries]) => addNaturalEarthMap(land, boundaries))
      .catch((error: unknown) => {
        if (!mapAbortController.signal.aborted) {
          console.error('Login3DGlobe: failed to load Natural Earth land data.', error);
        }
      });



    // THIẾT LẬP VÒNG QUỸ ĐẠO BAY XUNG QUANH QUẢ CẦU (TELEMETRY ORBITS)
    const orbitGroup = new THREE.Group();
    const createOrbit = (radius: number, color: number, rotationX: number, rotationY: number) => {
      const points: THREE.Vector3[] = [];
      const segments = 64;
      for (let i = 0; i <= segments; i++) {
        const theta = (i / segments) * Math.PI * 2;
        points.push(new THREE.Vector3(Math.cos(theta) * radius, 0, Math.sin(theta) * radius));
      }
      const orbitGeo = new THREE.BufferGeometry().setFromPoints(points);
      const orbitMat = new THREE.LineBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.12
      });
      const orbitLine = new THREE.LineLoop(orbitGeo, orbitMat);
      orbitLine.rotation.x = rotationX;
      orbitLine.rotation.y = rotationY;
      return orbitLine;
    };

    const orbit1 = createOrbit(globeRadius + 0.4, 0x00d2ff, Math.PI / 4, Math.PI / 6);
    const orbit2 = createOrbit(globeRadius + 0.7, 0x38bdf8, -Math.PI / 3, Math.PI / 4);
    const orbit3 = createOrbit(globeRadius + 1.1, 0x6366f1, Math.PI / 2, 0);

    orbitGroup.add(orbit1);
    orbitGroup.add(orbit2);
    orbitGroup.add(orbit3);
    globeGroup.add(orbitGroup);

    // THIẾT LẬP HẠT BỤI KHÔNG GIAN FLOATING (SPACE DUST)
    const dustGeometry = new THREE.BufferGeometry();
    const dustCount = 350;
    const dustPositions = new Float32Array(dustCount * 3);
    for (let i = 0; i < dustCount; i++) {
      const r = globeRadius + 1 + Math.random() * 3.5;
      const u = Math.random();
      const v = Math.random();
      const theta = u * 2.0 * Math.PI;
      const phi = Math.acos(2.0 * v - 1.0);

      dustPositions[i * 3] = r * Math.sin(phi) * Math.sin(theta);
      dustPositions[i * 3 + 1] = r * Math.cos(phi);
      dustPositions[i * 3 + 2] = r * Math.sin(phi) * Math.cos(theta);
    }
    dustGeometry.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3));
    const dustMaterial = new THREE.PointsMaterial({
      color: 0x00d2ff,
      size: 0.04,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending
    });
    const dustParticles = new THREE.Points(dustGeometry, dustMaterial);
    globeGroup.add(dustParticles);

    type BranchBeacon = {
      container: THREE.Group;
      branch: BranchOffice;
      core: THREE.Mesh;
      hitTarget: THREE.Mesh;
      pulseRings: THREE.Mesh[];
      pulseMaterials: THREE.MeshBasicMaterial[];
      phase: number;
    };

    // Each active office has a distinct phase so the five locations feel live
    // without flashing together.
    const branchBeacons: BranchBeacon[] = SEALINK_BRANCHES.map((branch) => {
      const location = geoToCartesian(branch.latitude, branch.longitude);
      const normal = new THREE.Vector3(location.x, location.y, location.z).normalize();
      const beacon = new THREE.Group();
      beacon.position.copy(normal).multiplyScalar(globeRadius + 0.035);
      beacon.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
      beacon.userData.branch = branch;

      const beam = new THREE.Mesh(
        new THREE.CylinderGeometry(0.012, 0.028, 0.36, 10),
        new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.68, blending: THREE.AdditiveBlending }),
      );
      beam.rotation.x = Math.PI / 2;
      beam.position.z = 0.20;
      beacon.add(beam);

      const core = new THREE.Mesh(
        new THREE.SphereGeometry(0.067, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0xe0fbff, transparent: true, opacity: 1, blending: THREE.AdditiveBlending }),
      );
      core.position.z = 0.04;
      beacon.add(core);

      // A transparent target gives each small beacon a comfortable hover area.
      const hitTarget = new THREE.Mesh(
        new THREE.SphereGeometry(0.19, 12, 12),
        new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
      );
      hitTarget.position.z = 0.10;
      hitTarget.userData.branch = branch;
      beacon.add(hitTarget);

      const pulseRings: THREE.Mesh[] = [];
      const pulseMaterials: THREE.MeshBasicMaterial[] = [];
      for (let ringIndex = 0; ringIndex < 2; ringIndex += 1) {
        const material = new THREE.MeshBasicMaterial({
          color: ringIndex === 0 ? 0x22d3ee : 0x60a5fa,
          transparent: true,
          opacity: 0.46,
          side: THREE.DoubleSide,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        const ring = new THREE.Mesh(new THREE.RingGeometry(0.09, 0.118, 32), material);
        ring.position.z = 0.055;
        beacon.add(ring);
        pulseRings.push(ring);
        pulseMaterials.push(material);
      }

      globeGroup.add(beacon);
      return { container: beacon, branch, core, hitTarget, pulseRings, pulseMaterials, phase: branch.pulseOffset };
    });

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enableZoom = false;
    const markerWorldPosition = new THREE.Vector3();
    const markerDirection = new THREE.Vector3();
    const markerScreenPosition = new THREE.Vector3();
    const cameraWorldPosition = new THREE.Vector3();
    const pointerPosition = new THREE.Vector2(-10000, -10000);
    let pointerInside = false;
    let activeBranchId: string | null = null;

    const clearActiveBranch = () => {
      if (activeBranchId === null && !branchHoverActiveRef.current) return;
      activeBranchId = null;
      branchHoverActiveRef.current = false;
      renderer.domElement.style.cursor = 'grab';
      setHoveredBranch(null);
    };

    const activateBranch = (branch: BranchOffice, x: number, y: number, bounds: DOMRect) => {
      branchHoverActiveRef.current = true;
      renderer.domElement.style.cursor = 'pointer';
      if (activeBranchId === branch.id) return;
      activeBranchId = branch.id;
      setImageFailed(false);
      setHoveredBranch(branch);
      const cardX = x + 28 + 236 <= bounds.width - 12 ? x + 28 : x - 264;
      const cardY = y - 169 >= 12 ? y - 169 : y + 28;
      setHoverPosition({
        x: Math.min(Math.max(12, cardX), Math.max(12, bounds.width - 248)),
        y: Math.min(Math.max(12, cardY), Math.max(12, bounds.height - 169)),
      });
    };

    const handlePointerMove = (event: PointerEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointerPosition.set(event.clientX - bounds.left, event.clientY - bounds.top);
      pointerInside = true;
    };

    const handlePointerLeave = () => {
      pointerInside = false;
      pointerPosition.set(-10000, -10000);
      clearActiveBranch();
    };

    renderer.domElement.style.cursor = 'grab';
    renderer.domElement.addEventListener('pointermove', handlePointerMove);
    renderer.domElement.addEventListener('pointerleave', handlePointerLeave);
    renderer.domElement.addEventListener('pointercancel', handlePointerLeave);

    const updateBranchTargetsAndHover = () => {
      const bounds = renderer.domElement.getBoundingClientRect();
      camera.getWorldPosition(cameraWorldPosition).normalize();
      let nearestBranch: BranchOffice | null = null;
      let nearestX = 0;
      let nearestY = 0;
      let nearestDistanceSq = 64 * 64;

      for (const beacon of branchBeacons) {
        beacon.hitTarget.getWorldPosition(markerWorldPosition);
        markerDirection.copy(markerWorldPosition).normalize();
        const isFrontFacing = markerDirection.dot(cameraWorldPosition) > 0.08;
        markerScreenPosition.copy(markerWorldPosition).project(camera);
        const isInView = markerScreenPosition.z >= -1 && markerScreenPosition.z <= 1;
        const isVisible = isFrontFacing && isInView;
        beacon.container.visible = isVisible;

        const target = branchTargetRefs.current[beacon.branch.id];
        const x = ((markerScreenPosition.x + 1) / 2) * bounds.width;
        const y = ((1 - markerScreenPosition.y) / 2) * bounds.height;
        if (target) target.style.display = isVisible ? 'block' : 'none';
        if (isVisible) {
          if (target) target.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`;
          if (pointerInside) {
            const distanceX = pointerPosition.x - x;
            const distanceY = pointerPosition.y - y;
            const distanceSq = distanceX * distanceX + distanceY * distanceY;
            if (distanceSq <= nearestDistanceSq) {
              nearestDistanceSq = distanceSq;
              nearestBranch = beacon.branch;
              nearestX = x;
              nearestY = y;
            }
          }
        }
      }

      if (nearestBranch) activateBranch(nearestBranch, nearestX, nearestY, bounds);
      else clearActiveBranch();
    };
    const clock = new THREE.Clock();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let animationFrame = 0;
    let motionScale = 1;
    let pulseTime = 0;

    const animate = () => {
      if (document.hidden) {
        animationFrame = 0;
        return;
      }
      animationFrame = requestAnimationFrame(animate);
      const delta = Math.min(clock.getDelta(), 0.05);
      const targetMotion = branchHoverActiveRef.current ? 0 : (reducedMotion.matches ? 0.18 : 1);
      const transition = 1 - Math.exp(-delta * 4.5);
      motionScale += (targetMotion - motionScale) * transition;
      const motion = motionScale;
      pulseTime += delta * motion;

      // Quả địa cầu xoay tự nhiên liên tục
      globeGroup.rotation.y += 0.072 * delta * motion;

      orbit1.rotation.y += 0.09 * delta * motion;
      orbit2.rotation.y -= 0.12 * delta * motion;
      orbit3.rotation.x += 0.048 * delta * motion;
      dustParticles.rotation.y -= 0.024 * delta * motion;

      // Xoay vệ tinh quanh quỹ đạo và tự xoay quanh thân
      branchBeacons.forEach((beacon) => {
        beacon.pulseRings.forEach((ring, ringIndex) => {
          const cycle = (pulseTime * 0.42 + beacon.phase + ringIndex * 0.48) % 1;
          const scale = 1 + cycle * 2.7;
          ring.scale.set(scale, scale, 1);
          beacon.pulseMaterials[ringIndex].opacity = Math.max(0, 0.48 * (1 - cycle));
        });
        const coreScale = 1 + Math.sin(pulseTime * 2.4 + beacon.phase * Math.PI * 2) * 0.12;
        beacon.core.scale.setScalar(coreScale);
      });

      controls.enabled = !branchHoverActiveRef.current;
      controls.update();
      updateBranchTargetsAndHover();
      renderer.render(scene, camera);
    };
    animate();
    const handleVisibilityChange = () => {
      if (!document.hidden && animationFrame === 0) animate();
    };

    const handleResize = () => {
      const width = mount.clientWidth;
      const height = mount.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener('resize', handleResize);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      disposed = true;
      mapAbortController.abort();
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      renderer.domElement.removeEventListener('pointermove', handlePointerMove);
      renderer.domElement.removeEventListener('pointerleave', handlePointerLeave);
      renderer.domElement.removeEventListener('pointercancel', handlePointerLeave);
      cancelAnimationFrame(animationFrame);
      controls.dispose();
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
      scene.traverse((object) => {
        const renderable = object as THREE.Object3D & {
          geometry?: THREE.BufferGeometry;
          material?: THREE.Material | THREE.Material[];
        };
        renderable.geometry?.dispose();
        const materials = Array.isArray(renderable.material) ? renderable.material : [renderable.material];
        materials.forEach((material) => material?.dispose());
      });
      renderer.renderLists.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div className="w-full h-full relative">
      <div ref={mountRef} className="w-full h-full" />
      {SEALINK_BRANCHES.map((branch) => (
        <span
          key={branch.id}
          ref={(node) => { branchTargetRefs.current[branch.id] = node; }}
          data-branch-target={branch.id}
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            display: 'none',
            width: 2,
            height: 2,
            pointerEvents: 'none',
            transform: 'translate(-9999px, -9999px)',
          }}
        />
      ))}
      {hoveredBranch && (
        <div
          data-branch-card={hoveredBranch.id}
          role="status"
          aria-live="polite"
          style={{
            position: 'absolute',
            left: hoverPosition.x,
            top: hoverPosition.y,
            width: 236,
            overflow: 'hidden',
            pointerEvents: 'none',
            border: '1px solid rgba(34, 211, 238, 0.72)',
            borderRadius: 12,
            background: 'rgba(2, 12, 27, 0.94)',
            boxShadow: '0 16px 34px rgba(0, 0, 0, 0.42)',
            color: '#e0fbff',
            zIndex: 20,
          }}
        >
          {hoveredBranch.imageUrl && !imageFailed ? (
            <img
              src={hoveredBranch.imageUrl}
              alt={`Chi nhánh Sealink tại ${hoveredBranch.country}`}
              onError={() => setImageFailed(true)}
              style={{ display: 'block', width: '100%', height: 96, objectFit: 'cover' }}
            />
          ) : (
            <div style={{ height: 96, display: 'grid', placeItems: 'center', background: 'linear-gradient(135deg, #0f2d4e, #123b5d)', fontWeight: 800, letterSpacing: '0.08em' }}>
              {hoveredBranch.country}
            </div>
          )}
          <div style={{ padding: '10px 12px 12px' }}>
            <div style={{ fontSize: 13, fontWeight: 800 }}>{hoveredBranch.label}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 5, color: '#67e8f9', fontSize: 11, fontWeight: 700 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#34d399', boxShadow: '0 0 10px #34d399' }} />
              ĐANG HOẠT ĐỘNG · {hoveredBranch.country}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
