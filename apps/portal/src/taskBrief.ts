import prompts from "./publicTaskPrompts.json";

/** Public instructions describe the job; only the tutorial teaches the rule. */
export function taskBrief(s: any, title: string): string {
  return (prompts as Record<string, string>)[String(s.task_id)] || `按照教程视频演示的规则完成“${title}”，并保存操作结果。`;
}
