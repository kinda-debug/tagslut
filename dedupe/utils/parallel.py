import concurrent.futures
import logging
import multiprocessing
import time
from typing import Callable, Iterable, List, TypeVar, Any, Optional

logger = logging.getLogger("dedupe")

T = TypeVar("T")
R = TypeVar("R")

def process_map(
    func: Callable[[T], R],
    items: Iterable[T],
    max_workers: Optional[int] = None,
    chunk_size: int = 1,
    progress: bool = False,
    progress_interval: int = 250,
) -> List[R]:
    """
    Applies `func` to every item in `items` using a process pool.

    Args:
        func: Worker function.
        items: Iterable of work items.
        max_workers: Number of processes. Defaults to CPU count - 1.
        chunk_size: Passed through to executor.map.
        progress: If True, logs progress periodically.
        progress_interval: Emit a progress log every N items.
    """
    if max_workers is None:
        # Leave one core free for system/DB ops
        max_workers = max(1, multiprocessing.cpu_count() - 1)

    results: List[R] = []
    
    item_list = list(items) 
    if not item_list:
        return []

    total = len(item_list)

    logger.info(f"Starting parallel processing with {max_workers} workers for {total} items.")

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            results_iter = executor.map(func, item_list, chunksize=chunk_size)

            start_ts = time.time()
            try:
                for idx, res in enumerate(results_iter, start=1):
                    results.append(res)
                    if progress and (idx % progress_interval == 0 or idx == total):
                        elapsed = max(0.001, time.time() - start_ts)
                        rate = idx / elapsed
                        logger.info(
                            "Progress: %d/%d (%.1f%%) | %.1f items/s | %.1fs elapsed",
                            idx,
                            total,
                            (idx / total) * 100,
                            rate,
                            elapsed,
                        )
            except KeyboardInterrupt:
                logger.warning(
                    "Parallel processing interrupted by user. Returning %d/%d partial results.",
                    len(results),
                    total,
                )
                return results
    except Exception as e:
        logger.error(f"Parallel processing failed: {e}")
        raise

    return results
