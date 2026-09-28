// import React, { useEffect, useRef } from 'react';

// interface ThinkingOrbProps {
//   size?: number;
//   color?: string;
//   speed?: number;
// }

// export const CustomThinkingOrb: React.FC<ThinkingOrbProps> = ({
//   size = 32,
//   color = '#FFFFFF',
//   speed = 1,
// }) => {
//   const canvasRef = useRef<HTMLCanvasElement | null>(null);

//   useEffect(() => {
//     const canvas = canvasRef.current;
//     if (!canvas) return;
//     const ctx = canvas.getContext('2d');
//     if (!ctx) return;

//     // Handle high-DPI displays
//     const dpr = window.devicePixelRatio || 1;
//     canvas.width = size * dpr;
//     canvas.height = size * dpr;
//     ctx.scale(dpr, dpr);

//     // Generate points on a 3D sphere surface (Fibonacci Sphere)
//     const numPoints = 80;
//     const radius = size * 0.38;
//     const points: Array<{ x: number; y: number; z: number }> = [];

//     const phi = (1 + Math.sqrt(5)) / 2; // Golden ratio
//     for (let i = 0; i < numPoints; i++) {
//       const y = 1 - (i / (numPoints - 1)) * 2;
//       const radiusAtY = Math.sqrt(1 - y * y);
//       const theta = (2 * Math.PI * i) / phi;

//       points.push({
//         x: Math.cos(theta) * radiusAtY * radius,
//         y: y * radius,
//         z: Math.sin(theta) * radiusAtY * radius,
//       });
//     }

//     let animationFrameId: number;
//     let angleY = 0;
//     let angleX = 0;

//     const render = () => {
//       ctx.clearRect(0, 0, size, size);

//       angleY += 0.02 * speed;
//       angleX += 0.01 * speed;

//       const cosY = Math.cos(angleY);
//       const sinY = Math.sin(angleY);
//       const cosX = Math.cos(angleX);
//       const sinX = Math.sin(angleX);

//       const centerX = size / 2;
//       const centerY = size / 2;

//       // Rotate points and draw
//       points.forEach((p) => {
//         // Y-axis rotation
//         let x1 = p.x * cosY - p.z * sinY;
//         let z1 = p.z * cosY + p.x * sinY;

//         // X-axis rotation
//         let y1 = p.y * cosX - z1 * sinX;
//         let z2 = z1 * cosX + p.y * sinX;

//         // Perspective mapping & depth scaling
//         const depth = (z2 + radius) / (2 * radius); // Normalized depth [0..1]
//         const dotRadius = Math.max(0.6, depth * 1.8);
//         const alpha = Math.max(0.15, depth);

//         ctx.beginPath();
//         ctx.arc(centerX + x1, centerY + y1, dotRadius, 0, Math.PI * 2);
//         ctx.fillStyle = color;
//         ctx.globalAlpha = alpha;
//         ctx.fill();
//       });

//       ctx.globalAlpha = 1;
//       animationFrameId = requestAnimationFrame(render);
//     };

//     render();

//     return () => cancelAnimationFrame(animationFrameId);
//   }, [size, color, speed]);

//   return (
//     <canvas
//       ref={canvasRef}
//       style={{
//         width: `${size}px`,
//         height: `${size}px`,
//         display: 'inline-block',
//       }}
//     />
//   );
// };

// import React, { useEffect, useRef } from 'react';

// type ShapeType = 'point' | 'triangle' | 'cube' | 'hexagon';

// interface ThinkingOrbProps {
//     size?: number;
//     color?: string;
//     speed?: number;
//     shape?: ShapeType;
//     shapeSize?: number; // Optional multiplier for shape dimensions
// }

// export const CustomThinkingOrb: React.FC<ThinkingOrbProps> = ({
//     size = 32,
//     color = '#FFFFFF',
//     speed = 1,
//     shape = 'point',
//     shapeSize = 1,
// }) => {
//     const canvasRef = useRef<HTMLCanvasElement | null>(null);

//     useEffect(() => {
//         const canvas = canvasRef.current;
//         if (!canvas) return;
//         const ctx = canvas.getContext('2d');
//         if (!ctx) return;

//         // Handle high-DPI displays
//         const dpr = window.devicePixelRatio || 1;
//         canvas.width = size * dpr;
//         canvas.height = size * dpr;
//         ctx.scale(dpr, dpr);

//         // Generate points on a 3D sphere surface (Fibonacci Sphere)
//         const numPoints = 80;
//         const radius = size * 0.38;
//         const points: Array<{ x: number; y: number; z: number }> = [];

//         const phi = (1 + Math.sqrt(5)) / 2; // Golden ratio
//         for (let i = 0; i < numPoints; i++) {
//             const y = 1 - (i / (numPoints - 1)) * 2;
//             const radiusAtY = Math.sqrt(1 - y * y);
//             const theta = (2 * Math.PI * i) / phi;

//             points.push({
//                 x: Math.cos(theta) * radiusAtY * radius,
//                 y: y * radius,
//                 z: Math.sin(theta) * radiusAtY * radius,
//             });
//         }

//         let animationFrameId: number;
//         let angleY = 0;
//         let angleX = 0;

//         // Helper: draw a regular polygon
//         const drawPolygon = (
//             ctx: CanvasRenderingContext2D,
//             cx: number,
//             cy: number,
//             radius: number,
//             sides: number,
//             rotation: number = 0,
//             alpha: number = 1
//         ) => {
//             if (sides < 3) return;
//             ctx.beginPath();
//             for (let i = 0; i < sides; i++) {
//                 const angle = rotation + (i * 2 * Math.PI) / sides;
//                 const x = cx + radius * Math.cos(angle);
//                 const y = cy + radius * Math.sin(angle);
//                 if (i === 0) ctx.moveTo(x, y);
//                 else ctx.lineTo(x, y);
//             }
//             ctx.closePath();
//             ctx.globalAlpha = alpha;
//             ctx.fillStyle = color;
//             ctx.fill();
//         };

//         // Helper: draw a cube (square with perspective offset)
//         const drawCube = (
//             ctx: CanvasRenderingContext2D,
//             cx: number,
//             cy: number,
//             size: number,
//             rotation: number,
//             alpha: number
//         ) => {
//             const half = size / 2;
//             const offset = half * 0.4; // perspective offset

//             // Front face
//             ctx.globalAlpha = alpha;
//             ctx.fillStyle = color;
//             ctx.beginPath();
//             ctx.rect(cx - half, cy - half, size, size);
//             ctx.fill();

//             // Top face (simplified)
//             ctx.globalAlpha = alpha * 0.7;
//             ctx.beginPath();
//             ctx.moveTo(cx - half, cy - half);
//             ctx.lineTo(cx - half + offset, cy - half - offset);
//             ctx.lineTo(cx + half + offset, cy - half - offset);
//             ctx.lineTo(cx + half, cy - half);
//             ctx.closePath();
//             ctx.fill();

//             // Right face (simplified)
//             ctx.globalAlpha = alpha * 0.5;
//             ctx.beginPath();
//             ctx.moveTo(cx + half, cy - half);
//             ctx.lineTo(cx + half + offset, cy - half - offset);
//             ctx.lineTo(cx + half + offset, cy + half - offset);
//             ctx.lineTo(cx + half, cy + half);
//             ctx.closePath();
//             ctx.fill();
//         };

//         const render = () => {
//             ctx.clearRect(0, 0, size, size);

//             angleY += 0.02 * speed;
//             angleX += 0.01 * speed;

//             const cosY = Math.cos(angleY);
//             const sinY = Math.sin(angleY);
//             const cosX = Math.cos(angleX);
//             const sinX = Math.sin(angleX);

//             const centerX = size / 2;
//             const centerY = size / 2;

//             // Rotate points and draw
//             points.forEach((p, index) => {
//                 // Y-axis rotation
//                 let x1 = p.x * cosY - p.z * sinY;
//                 let z1 = p.z * cosY + p.x * sinY;

//                 // X-axis rotation
//                 let y1 = p.y * cosX - z1 * sinX;
//                 let z2 = z1 * cosX + p.y * sinX;

//                 // Perspective mapping & depth scaling
//                 const depth = (z2 + radius) / (2 * radius); // Normalized depth [0..1]
//                 const baseRadius = Math.max(0.6, depth * 1.8) * shapeSize;
//                 const alpha = Math.max(0.15, depth);

//                 const screenX = centerX + x1;
//                 const screenY = centerY + y1;

//                 // Individual rotation for shapes based on index and time
//                 const shapeRotation = (index * 0.5 + angleY * 0.8) % (Math.PI * 2);

//                 switch (shape) {
//                     case 'point':
//                         ctx.beginPath();
//                         ctx.arc(screenX, screenY, baseRadius, 0, Math.PI * 2);
//                         ctx.fillStyle = color;
//                         ctx.globalAlpha = alpha;
//                         ctx.fill();
//                         break;

//                     case 'triangle':
//                         drawPolygon(ctx, screenX, screenY, baseRadius * 2, 3, shapeRotation, alpha);
//                         break;

//                     case 'cube':
//                         drawCube(ctx, screenX, screenY, baseRadius * 2.5, shapeRotation, alpha);
//                         break;

//                     case 'hexagon':
//                         drawPolygon(ctx, screenX, screenY, baseRadius * 2, 6, shapeRotation, alpha);
//                         break;

//                     default:
//                         // Fallback to point
//                         ctx.beginPath();
//                         ctx.arc(screenX, screenY, baseRadius, 0, Math.PI * 2);
//                         ctx.fillStyle = color;
//                         ctx.globalAlpha = alpha;
//                         ctx.fill();
//                         break;
//                 }
//             });

//             ctx.globalAlpha = 1;
//             animationFrameId = requestAnimationFrame(render);
//         };

//         render();

//         return () => cancelAnimationFrame(animationFrameId);
//     }, [size, color, speed, shape, shapeSize]);

//     return (
//         <canvas
//             ref={canvasRef}
//             style={{
//                 width: `${size}px`,
//                 height: `${size}px`,
//                 display: 'inline-block',
//             }}
//         />
//     );
// };


import React, { useEffect, useRef } from 'react';

type ShapeType = 'point' | 'triangle' | 'roundedTriangle' | 'cube' | 'hexagon';
type RotationType = 'dualAxis' | 'yOnly' | 'xOnly' | 'wobble' | 'tumble' | 'pulse';

interface ThinkingOrbProps {
  size?: number;
  color?: string;
  speed?: number;
  shape?: ShapeType;
  shapeSize?: number; // Optional multiplier for shape dimensions
  rotation?: RotationType;
}

export const CustomThinkingOrb: React.FC<ThinkingOrbProps> = ({
  size = 32,
  color = '#FFFFFF',
  speed = 1,
  shape = 'point',
  shapeSize = 1,
  rotation = 'dualAxis',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Handle high-DPI displays
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    // Generate points on a 3D sphere surface (Fibonacci Sphere)
    const numPoints = 80;
    const radius = size * 0.38;
    const points: Array<{ x: number; y: number; z: number }> = [];

    const phi = (1 + Math.sqrt(5)) / 2; // Golden ratio
    for (let i = 0; i < numPoints; i++) {
      const y = 1 - (i / (numPoints - 1)) * 2;
      const radiusAtY = Math.sqrt(1 - y * y);
      const theta = (2 * Math.PI * i) / phi;

      points.push({
        x: Math.cos(theta) * radiusAtY * radius,
        y: y * radius,
        z: Math.sin(theta) * radiusAtY * radius,
      });
    }

    let animationFrameId: number;
    let angleY = 0;
    let angleX = 0;
    let time = 0;

    // Helper: draw a regular polygon
    const drawPolygon = (
      ctx: CanvasRenderingContext2D,
      cx: number,
      cy: number,
      radius: number,
      sides: number,
      rotation: number = 0,
      alpha: number = 1
    ) => {
      if (sides < 3) return;
      ctx.beginPath();
      for (let i = 0; i < sides; i++) {
        const angle = rotation + (i * 2 * Math.PI) / sides;
        const x = cx + radius * Math.cos(angle);
        const y = cy + radius * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.globalAlpha = alpha;
      ctx.fillStyle = color;
      ctx.fill();
    };

    // Helper: draw a rounded triangle using arcTo for smooth corners
    const drawRoundedTriangle = (
      ctx: CanvasRenderingContext2D,
      cx: number,
      cy: number,
      radius: number,
      rotation: number,
      alpha: number,
      cornerRadiusRatio: number = 0.3
    ) => {
      const sides = 3;
      const cornerRadius = radius * cornerRadiusRatio;

      // Compute the three vertices
      const vertices: Array<{ x: number; y: number }> = [];
      for (let i = 0; i < sides; i++) {
        const angle = rotation + (i * 2 * Math.PI) / sides - Math.PI / 2;
        vertices.push({
          x: cx + radius * Math.cos(angle),
          y: cy + radius * Math.sin(angle),
        });
      }

      // Compute the point along a segment at a given distance from a vertex
      const pointTowards = (
        from: { x: number; y: number },
        to: { x: number; y: number },
        distance: number
      ) => {
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const len = Math.hypot(dx, dy) || 1;
        const t = Math.min(distance / len, 0.5);
        return { x: from.x + dx * t, y: from.y + dy * t };
      };

      ctx.beginPath();

      // Start at the first corner's incoming point (midpoint along previous edge)
      const start = pointTowards(vertices[0], vertices[1], cornerRadius);
      ctx.moveTo(start.x, start.y);

      for (let i = 0; i < sides; i++) {
        const current = vertices[i];
        const next = vertices[(i + 1) % sides];
        const nextNext = vertices[(i + 2) % sides];

        // End point of the current edge (before the next corner's curve)
        const edgeEnd = pointTowards(next, current, cornerRadius);
        ctx.lineTo(edgeEnd.x, edgeEnd.y);

        // Control point = the vertex itself, end = point on the outgoing edge
        const curveEnd = pointTowards(next, nextNext, cornerRadius);
        ctx.arcTo(next.x, next.y, curveEnd.x, curveEnd.y, cornerRadius);
      }

      ctx.closePath();
      ctx.globalAlpha = alpha;
      ctx.fillStyle = color;
      ctx.fill();
    };

    // Helper: draw a cube (square with perspective offset)
    const drawCube = (
      ctx: CanvasRenderingContext2D,
      cx: number,
      cy: number,
      size: number,
      rotation: number,
      alpha: number
    ) => {
      const half = size / 2;
      const offset = half * 0.4; // perspective offset

      // Front face
      ctx.globalAlpha = alpha;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.rect(cx - half, cy - half, size, size);
      ctx.fill();

      // Top face (simplified)
      ctx.globalAlpha = alpha * 0.7;
      ctx.beginPath();
      ctx.moveTo(cx - half, cy - half);
      ctx.lineTo(cx - half + offset, cy - half - offset);
      ctx.lineTo(cx + half + offset, cy - half - offset);
      ctx.lineTo(cx + half, cy - half);
      ctx.closePath();
      ctx.fill();

      // Right face (simplified)
      ctx.globalAlpha = alpha * 0.5;
      ctx.beginPath();
      ctx.moveTo(cx + half, cy - half);
      ctx.lineTo(cx + half + offset, cy - half - offset);
      ctx.lineTo(cx + half + offset, cy + half - offset);
      ctx.lineTo(cx + half, cy + half);
      ctx.closePath();
      ctx.fill();
    };

    const render = () => {
      ctx.clearRect(0, 0, size, size);

      time += 0.016 * speed;

      // Compute rotation angles based on selected rotation type
      switch (rotation) {
        case 'dualAxis':
          angleY += 0.02 * speed;
          angleX += 0.01 * speed;
          break;

        case 'yOnly':
          angleY += 0.025 * speed;
          angleX = 0;
          break;

        case 'xOnly':
          angleY = 0;
          angleX += 0.025 * speed;
          break;

        case 'wobble':
          // Smooth back-and-forth sway on both axes
          angleY = Math.sin(time * 0.8) * 0.8;
          angleX = Math.cos(time * 0.6) * 0.4;
          break;

        case 'tumble':
          // Chaotic-looking but deterministic tumbling
          angleY = time * 0.9 + Math.sin(time * 1.7) * 0.5;
          angleX = time * 0.5 + Math.cos(time * 1.3) * 0.6;
          break;

        case 'pulse':
          // Slow continuous rotation combined with a breathing scale effect
          angleY += 0.015 * speed;
          angleX += 0.008 * speed;
          break;

        default:
          angleY += 0.02 * speed;
          angleX += 0.01 * speed;
          break;
      }

      const cosY = Math.cos(angleY);
      const sinY = Math.sin(angleY);
      const cosX = Math.cos(angleX);
      const sinX = Math.sin(angleX);

      const centerX = size / 2;
      const centerY = size / 2;

      // Global scale pulse for the 'pulse' rotation type
      const pulseScale =
        rotation === 'pulse' ? 1 + Math.sin(time * 1.5) * 0.08 : 1;

      // Rotate points and draw
      points.forEach((p, index) => {
        // Y-axis rotation
        let x1 = p.x * cosY - p.z * sinY;
        let z1 = p.z * cosY + p.x * sinY;

        // X-axis rotation
        let y1 = p.y * cosX - z1 * sinX;
        let z2 = z1 * cosX + p.y * sinX;

        // Apply pulse scaling
        x1 *= pulseScale;
        y1 *= pulseScale;
        z2 *= pulseScale;

        // Perspective mapping & depth scaling
        const depth = (z2 + radius) / (2 * radius); // Normalized depth [0..1]
        const baseRadius = Math.max(0.6, depth * 1.8) * shapeSize * pulseScale;
        const alpha = Math.max(0.15, depth);

        const screenX = centerX + x1;
        const screenY = centerY + y1;

        // Individual rotation for shapes based on index and time
        const shapeRotation = (index * 0.5 + angleY * 0.8) % (Math.PI * 2);

        switch (shape) {
          case 'point':
            ctx.beginPath();
            ctx.arc(screenX, screenY, baseRadius, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.globalAlpha = alpha;
            ctx.fill();
            break;

          case 'triangle':
            drawPolygon(ctx, screenX, screenY, baseRadius * 2, 3, shapeRotation, alpha);
            break;

          case 'roundedTriangle':
            drawRoundedTriangle(
              ctx,
              screenX,
              screenY,
              baseRadius * 2,
              shapeRotation,
              alpha,
              0.35
            );
            break;

          case 'cube':
            drawCube(ctx, screenX, screenY, baseRadius * 2.5, shapeRotation, alpha);
            break;

          case 'hexagon':
            drawPolygon(ctx, screenX, screenY, baseRadius * 2, 6, shapeRotation, alpha);
            break;

          default:
            // Fallback to point
            ctx.beginPath();
            ctx.arc(screenX, screenY, baseRadius, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.globalAlpha = alpha;
            ctx.fill();
            break;
        }
      });

      ctx.globalAlpha = 1;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => cancelAnimationFrame(animationFrameId);
  }, [size, color, speed, shape, shapeSize, rotation]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        display: 'inline-block',
      }}
    />
  );
};