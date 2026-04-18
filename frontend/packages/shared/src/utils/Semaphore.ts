type Release = () => void;

export class Semaphore {
  private current = 0;
  private readonly queue: Array<(release: Release) => void> = [];

  constructor(private readonly limit: number) {
    if (limit < 1) throw new Error('Semaphore limit must be >= 1');
  }

  get available(): number {
    return Math.max(0, this.limit - this.current);
  }

  get pending(): number {
    return this.queue.length;
  }

  acquire(): Promise<Release> {
    return new Promise((resolve) => {
      const tryAcquire = () => {
        if (this.current < this.limit) {
          this.current += 1;
          resolve(this.release.bind(this));
        } else {
          this.queue.push(() => {
            this.current += 1;
            resolve(this.release.bind(this));
          });
        }
      };
      tryAcquire();
    });
  }

  private release(): void {
    this.current -= 1;
    const next = this.queue.shift();
    if (next) next(this.release.bind(this));
  }
}
