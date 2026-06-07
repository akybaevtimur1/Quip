// Мок-воркер (временный, для разработки фронта без реального бэка).
// POST /api/mock/jobs → создаёт job; id кодирует время старта, чтобы GET считал прогресс.

export async function POST(): Promise<Response> {
  const id = `mock_${Date.now().toString(36)}`;
  return Response.json({ id, status: "queued", stage: "queued", progress: 0 }, { status: 202 });
}
