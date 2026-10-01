(() => {
  const choice = document.getElementById('cadDesignChoice');
  const newField = document.getElementById('cadNewDesignField');
  const newName = document.getElementById('cadDesignName');

  function syncNewDesignField() {
    if (!choice || !newField) return;
    const isNew = choice.value === '__new__';
    newField.classList.toggle('hidden', !isNew);
    if (newName) newName.required = isNew;
  }
  choice?.addEventListener('change', syncNewDesignField);
  syncNewDesignField();

  const toastEl = document.getElementById('toast');
  let toastTimer;
  function toast(message, isError = false) {
    if (!toastEl) return;
    clearTimeout(toastTimer);
    toastEl.textContent = message;
    toastEl.classList.toggle('error', isError);
    toastEl.classList.add('show');
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2400);
  }

  const editor = document.getElementById('cadVersionEditor');
  document.getElementById('cadSaveNotes')?.addEventListener('click', async (event) => {
    const btn = event.currentTarget;
    const designId = editor?.dataset.designId;
    const versionId = editor?.dataset.versionId;
    if (!designId || !versionId) return;
    const prior = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
      const response = await fetch(`/api/cad/${encodeURIComponent(designId)}/${encodeURIComponent(versionId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label: document.getElementById('cadEditLabel')?.value || '',
          change_summary: document.getElementById('cadEditSummary')?.value || '',
          notes: document.getElementById('cadEditNotes')?.value || '',
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not save revision notes.');
      toast('Revision notes saved.');
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = prior;
    }
  });

  const viewer = document.getElementById('cadViewer');
  if (!viewer) return;
  const status = document.getElementById('cadViewerStatus');
  const modelUrl = viewer.dataset.modelUrl;
  if (!modelUrl) return;

  function statusMessage(title, detail = '', error = false) {
    if (!status) return;
    status.classList.remove('hidden');
    status.classList.toggle('error', error);
    status.innerHTML = '';
    const strong = document.createElement('strong');
    strong.textContent = title;
    const span = document.createElement('span');
    span.textContent = detail;
    status.append(strong, span);
  }

  if (!window.THREE || !window.occtimportjs) {
    statusMessage(
      '3D viewer could not load.',
      'The CAD library files are loaded from jsDelivr. Check this computer’s internet connection, then refresh the page.',
      true
    );
    return;
  }

  const THREE = window.THREE;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.setClearColor(0xaeb6bd, 1);
  viewer.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 1000000);
  camera.up.set(0, 0, 1);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.screenSpacePanning = true;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x6f8190, 1.65));
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.15);
  keyLight.position.set(1, -1, 2);
  scene.add(keyLight);
  const fillLight = new THREE.DirectionalLight(0xbcd7ea, 0.8);
  fillLight.position.set(-2, 1, 1);
  scene.add(fillLight);

  const grid = new THREE.GridHelper(500, 20, 0xb8cbd9, 0xdce7ef);
  grid.rotation.x = Math.PI / 2;
  grid.material.opacity = 0.65;
  grid.material.transparent = true;
  scene.add(grid);

  let modelGroup = new THREE.Group();
  scene.add(modelGroup);
  let lastBounds = null;
  let wireframe = false;

  function resize() {
    const width = Math.max(1, viewer.clientWidth);
    const height = Math.max(1, viewer.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(viewer);
  resize();

  function materialForColor(color) {
    const c = color && color.length >= 3
      ? new THREE.Color(color[0], color[1], color[2])
      : new THREE.Color(0xb8cad8);

    // STEP files often arrive with pure-white face colors. Tone every face
    // down just a little so white parts remain light, but are easy to see
    // against the gray viewer background.
    c.multiplyScalar(0.86);

    return new THREE.MeshStandardMaterial({
      color: c,
      roughness: 0.78,
      metalness: 0.04,
      side: THREE.DoubleSide,
      wireframe,
    });
  }

  function buildMesh(geometryMesh) {
    const geometry = new THREE.BufferGeometry();
    const position = geometryMesh?.attributes?.position?.array;
    if (!position || !position.length) return null;
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(position, 3));
    const normal = geometryMesh?.attributes?.normal?.array;
    if (normal && normal.length) geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normal, 3));
    const rawIndex = geometryMesh?.index?.array;
    if (rawIndex && rawIndex.length) geometry.setIndex(Array.from(rawIndex));
    if (!normal || !normal.length) geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();

    const defaultMaterial = materialForColor(geometryMesh.color);
    const materials = [defaultMaterial];
    const faces = geometryMesh.brep_faces || [];
    if (faces.length && rawIndex?.length) {
      for (const face of faces) materials.push(materialForColor(face.color || geometryMesh.color));
      const triangleCount = rawIndex.length / 3;
      let triangleIndex = 0;
      let faceIndex = 0;
      while (triangleIndex < triangleCount) {
        let lastIndex;
        let materialIndex;
        if (faceIndex >= faces.length) {
          lastIndex = triangleCount;
          materialIndex = 0;
        } else if (triangleIndex < faces[faceIndex].first) {
          lastIndex = faces[faceIndex].first;
          materialIndex = 0;
        } else {
          lastIndex = faces[faceIndex].last + 1;
          materialIndex = faceIndex + 1;
          faceIndex += 1;
        }
        geometry.addGroup(triangleIndex * 3, (lastIndex - triangleIndex) * 3, materialIndex);
        triangleIndex = lastIndex;
      }
    }

    const mesh = new THREE.Mesh(geometry, materials.length > 1 ? materials : defaultMaterial);
    mesh.name = geometryMesh.name || 'CAD part';

    const edgesGeometry = new THREE.EdgesGeometry(geometry, 35);
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x34434d, transparent: true, opacity: 0.52 });
    const edges = new THREE.LineSegments(edgesGeometry, edgeMaterial);
    edges.userData.isCadEdge = true;
    mesh.add(edges);
    return mesh;
  }

  function fitModel() {
    if (!lastBounds || lastBounds.isEmpty()) return;
    const center = lastBounds.getCenter(new THREE.Vector3());
    const size = lastBounds.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 1);
    const fov = camera.fov * Math.PI / 180;
    let distance = (maxDim / 2) / Math.tan(fov / 2);
    distance *= 1.75;
    const direction = new THREE.Vector3(1.25, -1.25, 0.95).normalize();
    camera.position.copy(center).add(direction.multiplyScalar(distance));
    camera.near = Math.max(maxDim / 10000, 0.001);
    camera.far = Math.max(maxDim * 100, distance * 20);
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.minDistance = Math.max(maxDim * 0.01, 0.001);
    controls.maxDistance = maxDim * 100;
    controls.update();

    grid.scale.setScalar(Math.max(maxDim / 500, 0.02));
    grid.position.set(center.x, center.y, lastBounds.min.z - maxDim * 0.01);
  }

  document.getElementById('cadFitBtn')?.addEventListener('click', fitModel);
  document.getElementById('cadWireBtn')?.addEventListener('click', (event) => {
    wireframe = !wireframe;
    event.currentTarget.setAttribute('aria-pressed', wireframe ? 'true' : 'false');
    event.currentTarget.textContent = wireframe ? 'Solid View' : 'Wireframe';
    modelGroup.traverse((obj) => {
      if (obj.isMesh) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach((m) => { if (m) m.wireframe = wireframe; });
      }
      if (obj.userData?.isCadEdge) obj.visible = !wireframe;
    });
  });

  function disposeGroup(group) {
    group.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose?.();
      const mats = Array.isArray(obj.material) ? obj.material : (obj.material ? [obj.material] : []);
      mats.forEach((m) => m.dispose?.());
    });
  }

  async function loadModel() {
    statusMessage('Loading STEP file…', 'Downloading the saved version from the tracker.');
    try {
      const response = await fetch(modelUrl, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Could not load STEP file (${response.status}).`);
      const buffer = await response.arrayBuffer();
      if (buffer.byteLength > 55 * 1024 * 1024) {
        statusMessage('Parsing a large STEP file…', 'This may take a while and the page can pause briefly.');
      } else {
        statusMessage('Converting STEP to 3D…', 'OpenCascade is triangulating the CAD model in your browser.');
      }

      const occt = await window.occtimportjs({
        locateFile: (path) => `https://cdn.jsdelivr.net/npm/occt-import-js@0.0.22/dist/${path}`,
      });
      await new Promise((resolve) => setTimeout(resolve, 20));
      const result = occt.ReadStepFile(new Uint8Array(buffer), {
        linearUnit: 'millimeter',
        linearDeflectionType: 'bounding_box_ratio',
        linearDeflection: 0.001,
        angularDeflection: 0.5,
      });
      if (!result?.success) throw new Error('OpenCascade could not read this STEP file.');

      disposeGroup(modelGroup);
      scene.remove(modelGroup);
      modelGroup = new THREE.Group();
      scene.add(modelGroup);

      let meshCount = 0;
      for (const resultMesh of (result.meshes || [])) {
        const mesh = buildMesh(resultMesh);
        if (mesh) {
          modelGroup.add(mesh);
          meshCount += 1;
        }
      }
      if (!meshCount) throw new Error('The STEP file loaded but did not contain displayable mesh geometry.');

      lastBounds = new THREE.Box3().setFromObject(modelGroup);
      fitModel();
      status?.classList.add('hidden');
    } catch (err) {
      console.error(err);
      statusMessage('Could not display this STEP model.', err.message || String(err), true);
    }
  }

  function animate() {
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  animate();
  loadModel();
})();
