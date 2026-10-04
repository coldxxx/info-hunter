'use client';
import SourceDeleteDialog from './source-delete-dialog';
import SourceDetailView from './source-detail-view';
import SourceDirectoryView from './source-directory-view';
import {
  useSourceManager,
  type SourceManagerProps,
} from './use-source-manager';

export default function SourceManager(props: SourceManagerProps) {
  const controller = useSourceManager(props);
  const selected = controller.selectedId ? controller.selected : undefined;
  return (
    <section
      className={selected ? 'source-detail-page' : 'source-management'}
      aria-label={selected ? '信息源详情' : '来源管理'}
    >
      <SourceDeleteDialog {...controller} />
      {selected ? (
        <SourceDetailView {...props} {...controller} selected={selected} />
      ) : (
        <SourceDirectoryView {...props} {...controller} />
      )}
    </section>
  );
}
