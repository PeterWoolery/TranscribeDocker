export default function OptionField({ option, value, onChange }) {
  if (option.type === 'boolean') {
    return (
      <label className="field switch-field">
        <div className="switch-row">
          <span>{option.label}</span>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(option.key, e.target.checked)}
          />
        </div>
        <small>{option.help}</small>
      </label>
    )
  }

  if (option.type === 'select') {
    return (
      <label className="field">
        <span>{option.label}</span>
        <select value={value ?? option.default ?? ''} onChange={(e) => onChange(option.key, e.target.value)}>
          {(option.choices || []).map((choice) => (
            <option key={choice} value={choice}>{choice}</option>
          ))}
        </select>
        <small>{option.help}</small>
      </label>
    )
  }

  return (
    <label className="field">
      <span>{option.label}</span>
      <input
        type={option.type === 'number' ? 'number' : option.type === 'password' ? 'password' : 'text'}
        value={value ?? option.default ?? ''}
        min={option.min ?? undefined}
        max={option.max ?? undefined}
        onChange={(e) => onChange(option.key, option.type === 'number' ? Number(e.target.value) : e.target.value)}
      />
      <small>{option.help}</small>
    </label>
  )
}
