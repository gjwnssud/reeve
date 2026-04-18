import { Toaster as SonnerToaster, type ToasterProps } from 'sonner';

export function Toaster(props: ToasterProps) {
  return (
    <SonnerToaster
      richColors
      closeButton
      position="top-right"
      toastOptions={{
        classNames: {
          toast: 'bg-background text-foreground border border-border shadow-lg',
        },
      }}
      {...props}
    />
  );
}

export { toast } from 'sonner';
