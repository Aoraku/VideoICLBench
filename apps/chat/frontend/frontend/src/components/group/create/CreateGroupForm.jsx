/**
 * @param {{
 *   name: string,
 *   onNameChange: (v: string) => void,
 *   canSubmit: boolean,
 *   loading: boolean,
 *   onSubmit: (e: import('react').FormEvent) => void,
 * }} props
 */
export default function CreateGroupForm({ name, onNameChange, canSubmit, loading, onSubmit }) {
  return (
    <form className="groupCreateForm" onSubmit={onSubmit}>
      <label className="groupCreateForm__field">
        <span className="groupCreateForm__label">群聊名称（可留空自动生成）</span>
        <input
          className="wxSearchInput"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="例如：项目周会"
          maxLength={50}
        />
      </label>
      <button type="submit" className="wxBtn wxBtn--primary" disabled={!canSubmit || loading}>
        {loading ? '创建中…' : '创建群聊'}
      </button>
    </form>
  )
}
