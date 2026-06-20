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
  // clipId is the INITIAL clip — switching clips happens in-page (no remount),
  // ClipEditorScreen holds the active clip in state and shallow-updates the URL.
  return <ClipEditorScreen jobId={jobId} initialClipId={clipId} />;
}
