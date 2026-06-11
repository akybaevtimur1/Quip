import ClipEditorScreen from "@/components/editor/ClipEditorScreen";

// Страница редактора клипа. Работает с ПРЯМОГО URL (закладка/F5): все данные
// фетчатся по params, зависимости от стейта главной нет. Возврат — /?job=<id>
// (deep-link главной восстанавливает грид из воркера).
export default async function EditPage({
  params,
}: {
  params: Promise<{ jobId: string; clipId: string }>;
}) {
  const { jobId, clipId } = await params;
  return <ClipEditorScreen jobId={jobId} clipId={clipId} />;
}
