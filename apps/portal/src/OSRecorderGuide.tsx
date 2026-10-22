export type OSGuide={apps:string[];entry:string;output_format?:string;inputs:string[];outputs:string[];preserve:string;finish:string;steps:{title:string;where:string;action:string;expected:string|null}[]};
export type OSExample={seed:number;instruction:string;steps:Record<string,unknown>[];guide?:OSGuide};

export function OSRecorderGuide({examples,activeGroup=0}:{examples:OSExample[];activeGroup?:number}){
 return <section className="os-recorder-guide" aria-label="OS 人工录制操作说明">
  <h3>在哪里操作</h3>
  <p>所有操作都在「预览示范环境」或「开始录制」打开的 OS 桌面标签页内完成，不在自己电脑的系统设置里操作。桌面外观相同，每题加载各自的材料；同题 A/B/C 共用初始材料，操作方法不同。</p>
  {examples.map((example,index)=>example.guide&&<details key={example.seed} open={index===activeGroup}>
   <summary>第 {index+1} 组 · {example.guide.apps.join(' → ')} · 点击查看操作路径</summary>
   <p><strong>从这里进入：</strong>{example.guide.entry}</p>
   {example.guide.outputs.length>0&&<p><strong>保存到：</strong><span style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{example.guide.outputs.join('\n')}</span></p>}
   {example.guide.output_format&&<section aria-label="输出格式"><h4>结果文件怎么填写</h4><p>结果文件可以从空白开始；按以下格式写入本组材料的处理结果，不是复制输入文件。</p><p style={{whiteSpace:'pre-wrap'}}>{example.guide.output_format}</p><p>下方直接列出本组完整保存示例。请在应用中展示输入与处理过程，只录 OS 应用标签页，不录此规则卡。</p></section>}
   <ol>{example.guide.steps.map((step,i)=><li key={i}>
    <strong>{step.title}</strong><p style={{overflowWrap:'anywhere'}}>{step.where}</p><p style={{overflowWrap:'anywhere'}}>{step.action}</p>
    {step.expected!==null&&<details open={Boolean(example.guide?.output_format)}><summary>本组完整保存示例（仅录制者可见）</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{step.expected.replaceAll('\f','【此处为分页符，用 Insert page break 插入】')}</pre></details>}
   </li>)}</ol>
   <p>{example.guide.preserve}</p><p>{example.guide.finish}</p>
  </details>)}
 </section>;
}
