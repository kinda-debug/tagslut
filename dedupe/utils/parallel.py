import concurrent.futures
import logging
import multiprocessing
from typing import Callable, Iterable, List, TypeVar, Any, Optional

logger = logging.getLogger("dedupe")

T = TypeVar("T")
R = TypeVar("R")

def process_map(
    func: Callable[[T], R],
    items: Iterable[T],
    max_workers: Optional[int] = None,
    chunk_size: int = 1
) -> List[R]:
    """
    Applies `func` to every item in `items` using a process pool.
    """
    if max_workers is None:
        # Leave one core free for system/DB ops
        max_workers = max(1, multiprocessing.cpu_count() - 1)

    results: List[R] = []
    
    item_list = list(items) 
    if not item_list:
        return []

    logger.info(f"Starting parallel processing with {max_workers} workers for {len(item_list)} items.")

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            # We use map to maintain order
            results_iter = executor.map(func, item_list, chunksize=chunk_size)
            results = list(results_iter)
    except KeyboardInterrupt:
        logger.warning("Parallel processing interrupted by user.")
        raise
    except Exception as e:
        logger.error(f"Parallel processing failed: {e}")
        raise

    return results
