import { command, getState, imLink } from './native.js';
const root = location.pathname.match(/^\/native\/music\/[a-f0-9]{32}\//)[0];
const playlist = document.querySelector('#projectPlaylist')?.dataset.id;
const selected = () => [...document.querySelectorAll('input[name="song"]:checked')].map(el => el.value);
const status = text => document.querySelectorAll('.music-status').forEach(el => el.textContent = text);
const action = (op, target, data = {}) => command(op, target, JSON.stringify(data));
const reload = async (op, target = playlist, data = {}) => { if (await action(op, target, data)) location.reload(); };
document.querySelectorAll('[data-open-im]').forEach(link => link.href = imLink());
document.querySelector('#selectAllSongs')?.addEventListener('change', e => document.querySelectorAll('input[name="song"]').forEach(input => input.checked = e.target.checked));
document.querySelector('#projectPlaylistCreate')?.addEventListener('submit', async e => {
  e.preventDefault(); const form = new FormData(e.target);
  const before = new Set(Object.keys(getState().world.playlists));
  if (await action('playlist.create', '', {activity:form.get('activity'), name:form.get('name')})) {
    const id = Object.keys(getState().world.playlists).find(id => !before.has(id));
    location.href = `${root}playlists/${id}/`;
  }
});
document.querySelector('#projectPlaylistRename')?.addEventListener('submit', async e => {
  e.preventDefault(); await reload('playlist.rename', playlist, {name:new FormData(e.target).get('name')});
});
const target = document.querySelector('#targetPlaylist');
target?.addEventListener('change', () => { document.querySelector('#openTargetPlaylist').href = target.value ? `${root}playlists/${target.value}/` : `${root}playlists/`; });
document.querySelector('#addSelectedSongs')?.addEventListener('click', async () => {
  if (!target.value || !selected().length) return status('请先选择目标歌单和要添加的歌曲。');
  if (await action('playlist.add', target.value, {songs:selected()})) {
    status('✓ 已加入目标歌单；请打开歌单核对并保存。');
    document.querySelectorAll('input[type="checkbox"]').forEach(el => el.checked = false);
  }
});
document.querySelector('#importSource')?.addEventListener('click', async e => {
  if (!target.value) return status('请先选择目标歌单。');
  if (await action('playlist.import', target.value, {source:e.currentTarget.dataset.source})) status('✓ 来源已导入，重复编号只保留一首。请打开歌单核对并保存。');
});
document.querySelector('#playlistImport')?.addEventListener('click', () => reload('playlist.import', playlist, {source:document.querySelector('#playlistSource').value}));
document.querySelector('#removeSelectedSongs')?.addEventListener('click', () => selected().length ? reload('playlist.remove', playlist, {songs:selected()}) : status('请先选择要移除的歌曲。'));
document.querySelectorAll('[data-project-remove]').forEach(button => button.onclick = () => reload('playlist.remove', playlist, {songs:[button.dataset.projectRemove]}));
document.querySelectorAll('[data-project-move]').forEach(button => button.onclick = () => {
  const ids = [...getState().world.playlists[playlist].members], i = ids.indexOf(button.dataset.target), j = i + Number(button.dataset.projectMove);
  if (j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]]; return reload('playlist.order', playlist, {songs:ids});
});
document.querySelector('#applyPlaylistSort')?.addEventListener('click', () => {
  const kind = document.querySelector('#playlistSort').value;
  if (!kind) return status('请选择排序方式。');
  const objects = getState().domain.objects, ids = [...getState().world.playlists[playlist].members];
  const compare = kind === 'year-asc' ? (a,b) => objects[a].year - objects[b].year : kind === 'duration-desc' ? (a,b) => objects[b].duration - objects[a].duration : (a,b) => objects[a].artist === objects[b].artist ? 0 : objects[a].artist < objects[b].artist ? 1 : -1;
  return reload('playlist.order', playlist, {songs:ids.sort(compare)});
});
document.querySelector('#saveProjectPlaylist')?.addEventListener('click', () => reload('playlist.save'));
document.querySelector('#shareProjectPlaylist')?.addEventListener('click', () => {
  const value = document.querySelector('#playlistShareGroup').value;
  return value ? reload('playlist.share', playlist, {group:Number(value)}) : status('请选择接收分享的活动群。');
});
document.querySelectorAll('[data-unshare]').forEach(button => button.onclick = () => reload('playlist.unshare', playlist, {share:button.dataset.unshare}));
document.querySelector('#deleteProjectPlaylist')?.addEventListener('click', async () => {
  if (confirm('删除此歌单？此操作不会删除资料库中的歌曲。') && await action('playlist.delete', playlist)) location.href = `${root}playlists/`;
});

document.querySelector('#addDetailSong')?.addEventListener('click', async e => {
  const id = document.querySelector('#songTargetPlaylist').value;
  if (await action('playlist.add', id, {songs:[e.currentTarget.dataset.song]})) status('✓ 已加入歌单，请打开歌单核对并保存。');
});
