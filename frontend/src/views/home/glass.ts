// The home page's glass ring (from the prototype built with Fable, backend/var/login-proto/phase2.html).
// A glass rod bent along a Lissajous curve in space: x = sin(a·s + δ), y = sin(b·s), depth = lift·sin(s + ψ), so at every
// crossing one strand really passes over the other. Drawn on the GPU in four passes:
//   S  soft-shadow field: distance from each pixel to the curve's outline (half resolution)
//   A  the strand nearest the eye at each pixel: every segment is a capsule, ray-cast from above (normal, arc position, height)
//   B  the strand behind it, so it can be seen through the one in front
//   C  the glass itself: tint, dark rim, Fresnel, studio lights, caustic; what lies behind is looked up bent, like through a lens
// a:b steps through a few figures and morphs point by point; 3:2 is the logo. The pointer tilts the whole thing.
const PI = Math.PI
// a, b, δ at rest, how far δ may wander before the figure folds onto itself, rod radius, depth phase, depth swing (last three / amplitude).
// ψ and lift keep the two strands at least a rod's width apart, front to back, at every crossing of the resting figure.
const SHAPES = [
  { a: 3, b: 2, d0: PI / 2, room: PI / 4, r: 0.085, psi: 0, lift: 0.25 },
  { a: 1, b: 2, d0: PI / 2, room: PI / 4, r: 0.09, psi: 0, lift: 0.22 },
  { a: 3, b: 4, d0: PI / 2, room: PI / 8, r: 0.058, psi: 0, lift: 0.25 },
  { a: 2, b: 3, d0: 0, room: PI / 6, r: 0.08, psi: PI / 2, lift: 0.23 },
  { a: 1, b: 1, d0: PI / 2, room: PI / 2, r: 0.09, psi: 0, lift: 0.18 },
]
const HOLD = 4.2, MORPH = 2, N = 1200, STRIDE = 15

const VS_SEG = `#version 300 es
layout(location=0) in vec2 aCorner;            // along, across: -1 or 1
layout(location=1) in vec3 aPrev;              // the point before this segment
layout(location=2) in vec3 aA;                 // segment ends: pixels (y down) and height towards the eye
layout(location=3) in vec3 aB;
layout(location=4) in vec3 aNext;              // the point after it
layout(location=5) in vec3 aArc;               // arc position at each end (0..1), tan(half the sharper bend at its ends)
uniform vec2 uRes; uniform float uCover;
out vec2 vP; flat out vec3 vA; flat out vec3 vB; flat out vec2 vArc; flat out vec3 vT0; flat out vec3 vT1;
void main() {
  vec2 t = aB.xy - aA.xy; float len = max(length(t), 1e-4); t /= len;
  float over = min(uCover, uCover * aArc.z + 1.5);           // fills the wedge on the outside of a bend
  vec2 p = (aA.xy + aB.xy) * .5 + t * aCorner.x * (len * .5 + over) + vec2(-t.y, t.x) * aCorner.y * uCover;
  vP = p; vA = aA; vB = aB; vArc = aArc.xy;
  vT0 = normalize(aB - aPrev); vT1 = normalize(aNext - aA);   // tangents at the two ends, shared with the neighbours
  gl_Position = vec4(p.x / uRes.x * 2. - 1., 1. - p.y / uRes.y * 2., 0., 1.);
}`
const FS_OUTLINE = `#version 300 es
precision highp float;
in vec2 vP; flat in vec3 vA; flat in vec3 vB; flat in vec2 vArc;
uniform float uR, uCover;
out vec4 o;
void main() {
  vec2 ba = vB.xy - vA.xy;
  vec2 off = vP - (vA.xy + ba * clamp(dot(vP - vA.xy, ba) / max(dot(ba, ba), 1e-8), 0., 1.));
  float q = dot(off, off);
  if (q >= uCover * uCover) discard;
  o = vec4(sqrt(q) / uR, 0., 0., 1.);
  gl_FragDepth = q / (uCover * uCover);
}`
const FS_ROD = `#version 300 es
precision highp float;
in vec2 vP; flat in vec3 vA; flat in vec3 vB; flat in vec2 vArc; flat in vec3 vT0; flat in vec3 vT1;
uniform float uR, uSame, uZScale; uniform bool uSecond; uniform highp sampler2D uFirst;
out vec4 o;
void main() {                                   // a ray straight down onto the capsule vA-vB
  vec3 ba = vB - vA, ro = vec3(vP, max(vA.z, vB.z) + 2. * uR), oa = ro - vA;
  float baba = dot(ba, ba), bard = -ba.z, baoa = dot(ba, oa), rdoa = -oa.z;
  float a = max(baba - bard * bard, 1e-6), b = baba * rdoa - baoa * bard, c = baba * dot(oa, oa) - baoa * baoa - uR * uR * baba;
  float h = b * b - a * c;
  if (h < 0.) discard;
  float t = (-b - sqrt(h)) / a, y = baoa + t * bard;
  if (y <= 0. || y >= baba) {                   // past an end: the rounded cap
    vec3 oc = y <= 0. ? oa : ro - vB;
    b = -oc.z; h = b * b - (dot(oc, oc) - uR * uR);
    if (h <= 0.) discard;
    t = -b - sqrt(h);
  }
  vec3 hit = ro - vec3(0., 0., t);
  float along = clamp(dot(hit - vA, ba) / baba, 0., 1.);
  vec3 tangent = normalize(mix(vT0, vT1, along)), rv = hit - vA - ba * along;
  vec3 n = normalize(rv - tangent * dot(rv, tangent));       // round about the blended tangent: no facets where segments meet
  float arc = mix(vArc.x, vArc.y, along);
  if (uSecond) {                                // only strands far along the curve from the one in front here
    vec4 f = texelFetch(uFirst, ivec2(gl_FragCoord.xy), 0);
    float away = abs(arc - f.z); away = min(away, 1. - away);
    if (f.z < 0. || away < uSame) discard;
  }
  o = vec4(n.xy, arc, hit.z / uR);
  gl_FragDepth = clamp(.5 - hit.z * uZScale, 0., 1.);
}`
const VS_QUAD = `#version 300 es
void main() { gl_Position = vec4(vec2(gl_VertexID == 1 ? 3. : -1., gl_VertexID == 2 ? 3. : -1.), 0., 1.); }`
const FS_SHADE = `#version 300 es
precision highp float;
uniform highp sampler2D uS, uA, uB; uniform vec2 uRes, uC; uniform float uR, uAmp, uSame;
out vec4 o;
const vec3 CYAN = vec3(.35, .78, .98), BLUE = vec3(0., .44, .89), VIOLET = vec3(.49, .30, .80);
const float DEPTH = .56, BEND = .78;
float sm(float a, float b, float x) { float t = clamp((x - a) / (b - a), 0., 1.); return t * t * (3. - 2. * t); }
ivec2 texel(vec2 p) { return ivec2(clamp(vec2(p.x, uRes.y - p.y), vec2(0.), uRes - 1.)); }
vec4 front(vec2 p) { return texelFetch(uA, texel(p), 0); }
vec4 back(vec2 p) { return texelFetch(uB, texel(p), 0); }
bool apart(float a, float b) { float d = abs(a - b); return min(d, 1. - d) > uSame; }
vec3 tintAt(vec2 p) {
  float g = clamp((.5 + ((p.x - uC.x) + (p.y - uC.y)) / (5.86 * uAmp) - .18) / .64, 0., 1.);
  vec3 c = g < .5 ? mix(CYAN, BLUE, g * 2.) : mix(BLUE, VIOLET, g * 2. - 1.);
  return c * DEPTH + (1. - DEPTH);
}
float blurred(vec2 p, float k) {                // the outline, softened by k pixels
  vec4 f = texelFetch(uS, texel(p) / 2, 0);
  return f.w < .5 ? 0. : 1. - sm(-k, k, (f.x - 1.) * uR);
}
vec3 paper(vec2 p) { return vec3(1.); }       // the page is white
vec3 ground(vec2 p) {                           // the paper with the glass's coloured shadow on it
  float soft = blurred(p - uAmp * vec2(.06, .11), uAmp * .11);
  float core = blurred(p - uAmp * vec2(.028, .055), uAmp * .04);
  return paper(p) * (1. - .16 * soft) * (1. - .5 * core * (1. - pow(tintAt(p), vec3(.9))));
}
float studio(vec3 n) {                          // sky dome, key soft box, its spill, a low strip light
  vec3 r = vec3(2. * n.z * n.x, 2. * n.z * n.y, 2. * n.z * n.z - 1.);
  vec3 key = normalize(vec3(-.26, -.36, .895)), strip = normalize(vec3(.62, .55, .56));
  return .22 + .78 * sm(-1., 1., -r.y) + 11. * sm(.925, .975, dot(r, key)) + 1.3 * sm(.35, 1., dot(r, key)) + 5. * sm(.90, .955, dot(r, strip));
}
vec3 glass(vec3 n, vec3 tint, out vec3 tr) {    // light the rod adds; tr = how much of what is behind comes through
  float fres = .04 + .96 * pow(1. - n.z, 4.);
  tr = pow(tint, vec3(.3 + .7 * n.z));
  tr *= (1. - sm(.5, .05, n.z) * (1. - .4 * tint * tint)) * (1. - fres);   // rays near the rim come from the dark sides
  float side = n.x * .585 + n.y * .811;
  float caustic = .6 * exp(-pow((side - .56) / .17, 2.)) * sm(.15, .55, n.z);
  float inner = .035 * (1. - fres) * min(studio(vec3(-n.xy, n.z)), 6.);
  return vec3(fres * studio(n)) + (caustic + inner) * (.45 + .55 * tint) + .015;
}
vec3 normalOf(vec4 L) { return vec3(L.xy, sqrt(max(1. - dot(L.xy, L.xy), 0.))); }
vec3 under(vec4 L, vec2 q) {                    // a strand seen through the one above: tinted body, no highlights, soft rim
  vec3 n = normalOf(L), g = ground(q);
  float body = sm(0., .55, 1. - length(L.xy));
  return mix(g, g * pow(tintAt(q), vec3(.6 + .6 * n.z)) * .9, .6 * body);
}
vec3 rodOnPaper(vec4 L, vec2 p, float veil) {   // one strand with only the paper behind it; veil thins it out
  vec3 n = normalOf(L), tr, add = glass(n, mix(tintAt(p), vec3(1.), veil), tr);
  vec3 col = ground(p - n.xy * uR * BEND) * tr + add * (1. - .5 * veil);
  // seen through another rod its outline would arrive as a jagged line: let it fade in from its rim instead
  return veil > 0. ? mix(ground(p), col, sm(0., .45, 1. - length(L.xy))) : col;
}
void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  ivec2 px = ivec2(gl_FragCoord.xy);
  vec4 F = texelFetch(uA, px, 0);
  vec3 bg = ground(p);
  o = vec4(bg, 1.);
  if (F.z < 0.) return;
  vec3 n = normalOf(F), tr, add = glass(n, tintAt(p), tr);
  vec2 s = p - n.xy * uR * BEND;                // where the rod's lens makes us look
  vec4 Fs = front(s), Bs = back(s);
  // the strand underneath shows through only as colour: its own highlights would read as stray stripes across this one
  vec3 behind = Fs.z >= 0. && apart(Fs.z, F.z) ? under(Fs, s) : Bs.z >= 0. ? under(Bs, s) : ground(s);
  vec3 col = behind * tr + add;
  float shade = 0.;                             // a strand passing overhead keeps some light off this one
  for (int i = 0; i < 16; i++) {                // two rings of taps round this pixel
    float a = float(i) * .7854 + (i < 8 ? .2 : .6), reach = i < 8 ? .8 : 1.7;
    vec4 T = front(p + vec2(cos(a), sin(a)) * uR * reach);
    if (T.z >= 0. && apart(T.z, F.z)) shade += sm(.3, 1.8, T.w - F.w) * (i < 8 ? .075 : .05);
  }
  col *= 1. - .42 * shade;
  float edge = clamp((1. - length(F.xy)) * uR + .25, 0., 1.);                  // soften the last pixel of the silhouette
  if (edge < 1.) {
    vec4 Bp = texelFetch(uB, px, 0);
    col = mix(Bp.z >= 0. ? rodOnPaper(Bp, p, 0.) : bg, col, edge);
  }
  o = vec4(col, 1.);
}`

type Program = { p: WebGLProgram; u: Record<string, WebGLUniformLocation | null> }
type Target = { tex: WebGLTexture; depth: WebGLRenderbuffer; fbo: WebGLFramebuffer; w: number; h: number }
const ease = (x: number) => x * x * (3 - 2 * x)

// Draws on the canvas until the returned stop() is called. Nothing (undefined) where the browser cannot: no WebGL 2,
// no float render targets, or the shaders do not build. lost() runs if the GPU drops the context later.
// Only while it can be seen (on screen, tab in front). With reduced motion it is one still picture: no tilt after the
// pointer, no frame loop; drawn again only when its size changes or a click asks for the next figure.
export function drawGlass(cv: HTMLCanvasElement, lost: () => void): (() => void) | undefined {
  const gl = cv.getContext('webgl2', { antialias: false, alpha: false })
  if (!gl || !(gl.getExtension('EXT_color_buffer_float') || gl.getExtension('EXT_color_buffer_half_float'))) return
  const frozen = matchMedia('(prefers-reduced-motion: reduce)').matches
  const start = frozen ? 0 : performance.now() / 1000
  let dpr = Math.min(devicePixelRatio || 1, 2), W = 0, H = 0, raf = 0, skip = 0
  let ptrX = 0, ptrY = 0, tx = 0, ty = 0
  let targets: Target[] = []

  function program(vs: string, fs: string): Program {
    const p = gl!.createProgram()
    for (const [type, src] of [[gl!.VERTEX_SHADER, vs], [gl!.FRAGMENT_SHADER, fs]] as const) {
      const s = gl!.createShader(type)!
      gl!.shaderSource(s, src)
      gl!.compileShader(s)
      if (!gl!.getShaderParameter(s, gl!.COMPILE_STATUS)) throw new Error(gl!.getShaderInfoLog(s) ?? 'shader')
      gl!.attachShader(p, s)
    }
    gl!.linkProgram(p)
    if (!gl!.getProgramParameter(p, gl!.LINK_STATUS)) throw new Error(gl!.getProgramInfoLog(p) ?? 'program')
    const u: Program['u'] = {}
    for (let i = 0; i < gl!.getProgramParameter(p, gl!.ACTIVE_UNIFORMS); i++) {
      const name = gl!.getActiveUniform(p, i)!.name
      u[name] = gl!.getUniformLocation(p, name)
    }
    return { p, u }
  }

  let outline: Program, rod: Program, shade: Program
  const quad = gl.createVertexArray(), inst = gl.createBuffer(), instData = new Float32Array(N * STRIDE)
  try {
    outline = program(VS_SEG, FS_OUTLINE)
    rod = program(VS_SEG, FS_ROD)
    shade = program(VS_QUAD, FS_SHADE)
  } catch (e) {
    console.error(e)
    return
  }
  gl.bindVertexArray(quad)
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
  gl.enableVertexAttribArray(0)
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
  gl.bindBuffer(gl.ARRAY_BUFFER, inst)
  gl.bufferData(gl.ARRAY_BUFFER, instData.byteLength, gl.DYNAMIC_DRAW)
  for (const loc of [1, 2, 3, 4, 5]) {
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, STRIDE * 4, (loc - 1) * 12)
    gl.vertexAttribDivisor(loc, 1)
  }
  gl.bindVertexArray(null)

  function resize() {
    W = Math.max(2, Math.round(cv.clientWidth * dpr))
    H = Math.max(2, Math.round(cv.clientHeight * dpr))
    cv.width = W
    cv.height = H
    for (const t of targets) {
      gl!.deleteTexture(t.tex)
      gl!.deleteRenderbuffer(t.depth)
      gl!.deleteFramebuffer(t.fbo)
    }
    targets = [[Math.ceil(W / 2), Math.ceil(H / 2)], [W, H], [W, H]].map(([w, h]) => { // S, A, B
      const tex = gl!.createTexture()
      gl!.bindTexture(gl!.TEXTURE_2D, tex)
      gl!.texImage2D(gl!.TEXTURE_2D, 0, gl!.RGBA16F, w, h, 0, gl!.RGBA, gl!.HALF_FLOAT, null)
      gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_MIN_FILTER, gl!.NEAREST)
      gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_MAG_FILTER, gl!.NEAREST)
      const depth = gl!.createRenderbuffer()
      gl!.bindRenderbuffer(gl!.RENDERBUFFER, depth)
      gl!.renderbufferStorage(gl!.RENDERBUFFER, gl!.DEPTH_COMPONENT24, w, h)
      const fbo = gl!.createFramebuffer()
      gl!.bindFramebuffer(gl!.FRAMEBUFFER, fbo)
      gl!.framebufferTexture2D(gl!.FRAMEBUFFER, gl!.COLOR_ATTACHMENT0, gl!.TEXTURE_2D, tex, 0)
      gl!.framebufferRenderbuffer(gl!.FRAMEBUFFER, gl!.DEPTH_ATTACHMENT, gl!.RENDERBUFFER, depth)
      return { tex, depth, fbo, w, h }
    })
  }

  const xs = new Float32Array(N), ys = new Float32Array(N), zs = new Float32Array(N), seg = new Float32Array(N), bend = new Float32Array(N)

  function frame(now: number) {
    const g = gl!
    const t = now - start + skip
    const cycle = HOLD + MORPH, k = Math.floor(t / cycle), into = t - k * cycle
    const from = SHAPES[k % SHAPES.length], to = SHAPES[(k + 1) % SHAPES.length]
    const m = into < HOLD ? 0 : ease((into - HOLD) / MORPH)

    tx += (ptrX - tx) * 0.06
    ty += (ptrY - ty) * 0.06
    const swayY = 0.13 * Math.sin(t * 0.5) + 0.32 * tx, swayX = 0.09 * Math.cos(t * 0.37) - 0.24 * ty // tilt: a slow sway, plus the pointer
    const cyw = Math.cos(swayY), syw = Math.sin(swayY), cxw = Math.cos(swayX), sxw = Math.sin(swayX)
    const wander = 0.12 * Math.sin(t * 0.7)
    const amp = Math.min(W, H) * 0.355, cx = W / 2, cy = H * 0.46
    const R = amp * (from.r + (to.r - from.r) * m)
    const da = from.d0 + wander * from.room, db = to.d0 + wander * to.room

    for (let i = 0; i < N; i++) {
      const s = (i / N) * 2 * PI
      const x = Math.sin(from.a * s + da) * (1 - m) + Math.sin(to.a * s + db) * m
      const y = Math.sin(from.b * s) * (1 - m) + Math.sin(to.b * s) * m
      const z = from.lift * Math.sin(s + from.psi) * (1 - m) + to.lift * Math.sin(s + to.psi) * m
      const x1 = x * cyw + z * syw, z1 = -x * syw + z * cyw // turn about the vertical axis, then the horizontal one
      xs[i] = cx + amp * x1
      ys[i] = cy + amp * (y * cxw - z1 * sxw)
      zs[i] = amp * (y * sxw + z1 * cxw)
    }
    let total = 0
    for (let i = 0; i < N; i++) {
      const j = (i + 1) % N
      seg[i] = Math.hypot(xs[j] - xs[i], ys[j] - ys[i], zs[j] - zs[i])
      total += seg[i]
      const h = (i + N - 1) % N, ax = xs[i] - xs[h], ay = ys[i] - ys[h], bx = xs[j] - xs[i], by = ys[j] - ys[i]
      bend[i] = Math.tan(Math.min(Math.abs(Math.atan2(ax * by - ay * bx, ax * bx + ay * by)), 2.6) / 2)
    }
    let arc = 0
    for (let i = 0; i < N; i++) {
      const h = (i + N - 1) % N, j = (i + 1) % N, l = (i + 2) % N, o = i * STRIDE, next = arc + seg[i] / total
      ;[h, i, j, l].forEach((q, n) => {
        instData[o + n * 3] = xs[q]
        instData[o + n * 3 + 1] = ys[q]
        instData[o + n * 3 + 2] = zs[q]
      })
      instData[o + 12] = arc
      instData[o + 13] = next
      instData[o + 14] = Math.max(bend[i], bend[j])
      arc = next
    }
    g.bindBuffer(g.ARRAY_BUFFER, inst)
    g.bufferSubData(g.ARRAY_BUFFER, 0, instData)
    g.bindVertexArray(quad)
    g.enable(g.DEPTH_TEST)
    g.depthFunc(g.LESS)
    g.clearDepth(1)
    const same = (10 * R) / total

    const [S, A, B] = targets
    g.bindFramebuffer(g.FRAMEBUFFER, S.fbo)
    g.viewport(0, 0, S.w, S.h)
    g.clearColor(0, 0, 0, 0)
    g.clear(g.COLOR_BUFFER_BIT | g.DEPTH_BUFFER_BIT)
    g.useProgram(outline.p)
    g.uniform2f(outline.u.uRes, W, H)
    g.uniform1f(outline.u.uR, R)
    g.uniform1f(outline.u.uCover, R + amp * 0.12)
    g.drawArraysInstanced(g.TRIANGLE_STRIP, 0, 4, N)

    g.useProgram(rod.p)
    g.viewport(0, 0, W, H)
    g.uniform2f(rod.u.uRes, W, H)
    g.uniform1f(rod.u.uR, R)
    g.uniform1f(rod.u.uCover, R + 1.5)
    g.uniform1f(rod.u.uSame, same)
    g.uniform1f(rod.u.uZScale, 0.5 / (amp * 1.4))
    g.uniform1i(rod.u.uFirst, 0)
    g.clearColor(0, 0, -1, 0)
    for (const second of [0, 1]) {
      g.bindFramebuffer(g.FRAMEBUFFER, (second ? B : A).fbo)
      g.clear(g.COLOR_BUFFER_BIT | g.DEPTH_BUFFER_BIT)
      g.uniform1i(rod.u.uSecond, second)
      g.activeTexture(g.TEXTURE0)
      g.bindTexture(g.TEXTURE_2D, second ? A.tex : null)
      g.drawArraysInstanced(g.TRIANGLE_STRIP, 0, 4, N)
    }

    g.bindFramebuffer(g.FRAMEBUFFER, null)
    g.disable(g.DEPTH_TEST)
    g.useProgram(shade.p)
    g.uniform2f(shade.u.uRes, W, H)
    g.uniform2f(shade.u.uC, cx, cy)
    g.uniform1f(shade.u.uR, R)
    g.uniform1f(shade.u.uAmp, amp)
    g.uniform1f(shade.u.uSame, same)
    ;([[S, 'uS'], [A, 'uA'], [B, 'uB']] as const).forEach(([target, name], i) => {
      g.activeTexture(g.TEXTURE0 + i)
      g.bindTexture(g.TEXTURE_2D, target.tex)
      g.uniform1i(shade.u[name], i)
    })
    g.drawArrays(g.TRIANGLES, 0, 3)
  }

  let slow = 0, counted = 0, last = 0
  function loop() { // the moving ring (not with reduced motion: drawStill)
    const now = performance.now() / 1000
    frame(now)
    if (dpr > 1 && counted < 90) { // a weak GPU: give up sharpness before smoothness
      if (last && now - last > 0.03) slow++
      if (++counted === 90 && slow > 45) {
        dpr = 1
        resize()
      }
    }
    last = now
    raf = requestAnimationFrame(loop)
  }

  try {
    resize()
  } catch (e) {
    console.error(e)
    return
  }
  const onPointer = (e: PointerEvent) => {
    ptrX = (e.clientX / innerWidth - 0.5) * 2
    ptrY = (e.clientY / innerHeight - 0.5) * 2
  }
  const drawStill = () => {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => frame(0))
  }
  const onClick = () => { // jump to the next figure
    if (frozen) {
      skip += HOLD + MORPH
      drawStill()
      return
    }
    const into = (performance.now() / 1000 - start + skip) % (HOLD + MORPH)
    if (into < HOLD) skip += HOLD - into
  }
  let onScreen = true
  const wake = () => { // draw only while it can be seen
    cancelAnimationFrame(raf)
    if (document.hidden || !onScreen) return
    if (frozen) drawStill()
    else {
      last = 0
      loop()
    }
  }
  const sized = new ResizeObserver(() => {
    resize() // which clears the canvas
    if (frozen) drawStill()
  })
  const seen = new IntersectionObserver(([e]) => {
    onScreen = e.isIntersecting
    wake()
  })
  const onLost = () => {
    stop()
    lost()
  }
  function stop() {
    cancelAnimationFrame(raf)
    sized.disconnect()
    seen.disconnect()
    removeEventListener('pointermove', onPointer)
    cv.removeEventListener('click', onClick)
    cv.removeEventListener('webglcontextlost', onLost)
    document.removeEventListener('visibilitychange', wake)
  }
  sized.observe(cv)
  seen.observe(cv)
  if (!frozen) addEventListener('pointermove', onPointer)
  cv.addEventListener('click', onClick)
  cv.addEventListener('webglcontextlost', onLost)
  document.addEventListener('visibilitychange', wake)
  wake()
  return () => {
    stop()
    gl.getExtension('WEBGL_lose_context')?.loseContext() // free the GPU now, not when the canvas is collected
  }
}
