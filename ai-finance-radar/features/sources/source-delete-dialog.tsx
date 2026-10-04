'use client';
import { Trash2 } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { SourceManagerController } from './use-source-manager';

type SourceDeleteDialogProps = Pick<
  SourceManagerController,
  | 'deleteTarget'
  | 'setDeleteTarget'
  | 'deleteError'
  | 'pendingAction'
  | 'deleteSource'
>;

export default function SourceDeleteDialog({
  deleteTarget,
  setDeleteTarget,
  deleteError,
  pendingAction,
  deleteSource,
}: SourceDeleteDialogProps) {
  return (
    <AlertDialog
      open={!!deleteTarget}
      onOpenChange={(open) => {
        if (!open && !pendingAction) setDeleteTarget(null);
      }}
    >
      <AlertDialogContent className="source-delete-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>删除来源？</AlertDialogTitle>
          <AlertDialogDescription>
            将从全局来源库删除「{deleteTarget?.config.name}
            」，停止后续采集并解除所有主题的关注。
          </AlertDialogDescription>
          <AlertDialogDescription>
            {deleteTarget?.topics.length
              ? `涉及主题：${deleteTarget.topics.map((t) => t.name).join('、')}。`
              : '此来源尚未被主题关注。'}
            历史归档、收藏和笔记会保留。重新添加该来源链接可恢复来源。
          </AlertDialogDescription>
        </AlertDialogHeader>
        {deleteError && (
          <p className="source-error" role="alert">
            {deleteError}
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pendingAction}>取消</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={pendingAction}
            onClick={() => void deleteSource()}
          >
            <Trash2 />
            {pendingAction ? '正在删除…' : '确认删除'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
