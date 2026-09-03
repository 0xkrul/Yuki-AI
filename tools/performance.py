import asyncio
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar
import discord
from discord.ext import commands

T = TypeVar('T')


class TimedLRUCache:
    """
    OPTIMIZATION: LRU cache with TTL (Time To Live)
    Automatically expires old entries to save memory
    """
    def __init__(self, maxsize: int = 128, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: Dict[Any, tuple] = {}  # key -> (value, timestamp)
        self._access_order = []  # Track LRU order
    
    def get(self, key: Any) -> Optional[Any]:
        """Get value from cache if exists and not expired"""
        if key not in self._cache:
            return None
        
        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            # Expired
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return None
        
        # Update access order (move to end)
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        
        return value
    
    def set(self, key: Any, value: Any):
        """Set value in cache"""
        # Check if we need to evict
        if len(self._cache) >= self.maxsize and key not in self._cache:
            # Remove least recently used
            if self._access_order:
                lru_key = self._access_order.pop(0)
                del self._cache[lru_key]
        
        self._cache[key] = (value, time.time())
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
        self._access_order.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)
    
    def cleanup_expired(self):
        """Remove all expired entries"""
        now = time.time()
        expired_keys = []
        for key, (value, timestamp) in self._cache.items():
            if now - timestamp > self.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)


class BatchProcessor:
    def __init__(self, flush_interval: float = 1.0, max_batch_size: int = 100):
        self.flush_interval = flush_interval
        self.max_batch_size = max_batch_size
        self._queue = []
        self._lock = asyncio.Lock()
        self._task = None
    
    async def add(self, operation: Callable, *args, **kwargs):
        """Add operation to batch queue"""
        async with self._lock:
            self._queue.append((operation, args, kwargs))
            
            if len(self._queue) >= self.max_batch_size:
                await self._flush()
    
    async def _flush(self):
        """Execute all queued operations"""
        if not self._queue:
            return
        
        operations = self._queue.copy()
        self._queue.clear()
        
        # Execute all operations in parallel
        tasks = [op(*args, **kwargs) for op, args, kwargs in operations]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def start_auto_flush(self):
        """Start automatic flushing on interval"""
        if self._task is not None:
            return
        
        async def _auto_flush():
            while True:
                await asyncio.sleep(self.flush_interval)
                async with self._lock:
                    await self._flush()
        
        self._task = asyncio.create_task(_auto_flush())
    
    async def stop_auto_flush(self):
        """Stop automatic flushing"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


class AsyncRateLimiter:
    """
    OPTIMIZATION: Memory-efficient rate limiter
    Uses sliding window for accurate rate limiting
    """
    def __init__(self, rate: int, per: float):
        """
        rate: number of operations
        per: time period in seconds
        """
        self.rate = rate
        self.per = per
        self._requests: Dict[Any, list] = {}
    
    async def acquire(self, key: Any) -> bool:
        """Try to acquire permission. Returns True if allowed, False if rate limited."""
        now = time.time()
        
        # Clean old requests
        if key in self._requests:
            self._requests[key] = [t for t in self._requests[key] if now - t < self.per]
        else:
            self._requests[key] = []
        
        # Check if rate limit exceeded
        if len(self._requests[key]) >= self.rate:
            return False
        
        # Add new request
        self._requests[key].append(now)
        return True
    
    def cleanup(self, age: float = 300):
        """Remove keys that haven't been used in 'age' seconds"""
        now = time.time()
        to_remove = []
        for key, requests in self._requests.items():
            if requests and now - requests[-1] > age:
                to_remove.append(key)
        
        for key in to_remove:
            del self._requests[key]


def async_cache(ttl: int = 300, maxsize: int = 128):
    """
    OPTIMIZATION: Decorator for caching async function results
    
    Usage:
        @async_cache(ttl=600, maxsize=256)
        async def expensive_operation(param):
            ...
    """
    cache = TimedLRUCache(maxsize=maxsize, ttl=ttl)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from arguments
            cache_key = (args, tuple(sorted(kwargs.items())))
            
            # Try cache first
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Cache miss - execute function
            result = await func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        # Add cache management methods
        wrapper.cache_clear = cache.clear
        wrapper.cache_size = cache.size
        wrapper.cache_cleanup = cache.cleanup_expired
        
        return wrapper
    return decorator


class MemoryMonitor:
    """
    OPTIMIZATION: Monitor memory usage and trigger cleanup when needed
    """
    def __init__(self, threshold_mb: int = 800):
        """threshold_mb: Memory limit in MB before triggering cleanup"""
        self.threshold_mb = threshold_mb
        self._cleanup_callbacks = []
    
    def register_cleanup(self, callback: Callable):
        """Register a cleanup callback to be called when memory is high"""
        self._cleanup_callbacks.append(callback)
    
    async def check_and_cleanup(self):
        """Check memory usage and run cleanup if needed"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.threshold_mb:
                print(f"⚠ Memory usage: {memory_mb:.1f}MB (threshold: {self.threshold_mb}MB)")
                print("Running cleanup callbacks...")
                
                for callback in self._cleanup_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback()
                        else:
                            callback()
                    except Exception as e:
                        print(f"Cleanup callback error: {e}")
                
                # Force garbage collection
                import gc
                gc.collect()
                
                new_memory = process.memory_info().rss / 1024 / 1024
                print(f"✓ Memory after cleanup: {new_memory:.1f}MB (freed: {memory_mb - new_memory:.1f}MB)")
        except ImportError:
            # psutil not available
            pass
    
    async def start_monitoring(self, interval: int = 60):
        """Start periodic memory monitoring"""
        while True:
            await asyncio.sleep(interval)
            await self.check_and_cleanup()


class DatabaseQueryOptimizer:
    """
    OPTIMIZATION: Helper for optimizing database queries
    """
    @staticmethod
    async def batch_fetch(pool, query: str, params_list: list) -> list:
        """
        Execute multiple queries in parallel
        
        Example:
            results = await DatabaseQueryOptimizer.batch_fetch(
                bot.db,
                "SELECT * FROM users WHERE id = $1",
                [(1,), (2,), (3,)]
            )
        """
        tasks = [pool.fetchrow(query, *params) for params in params_list]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    @staticmethod
    async def batch_execute(pool, query: str, params_list: list):
        """
        Execute multiple write queries efficiently using executemany
        
        Example:
            await DatabaseQueryOptimizer.batch_execute(
                bot.db,
                "INSERT INTO logs (user_id, action) VALUES ($1, $2)",
                [(1, "login"), (2, "logout"), (3, "login")]
            )
        """
        async with pool.acquire() as conn:
            await conn.executemany(query, params_list)
    
    @staticmethod
    def create_index_hint(table: str, columns: list) -> str:
        """Generate SQL for creating an index"""
        col_str = "_".join(columns)
        return f"CREATE INDEX IF NOT EXISTS idx_{table}_{col_str} ON {table} ({', '.join(columns)});"


class GuildDataCache:
    """
    OPTIMIZATION: Cache guild-specific data to reduce DB queries
    Useful for settings, prefixes, disabled commands, etc.
    """
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._cache: Dict[int, Dict[str, Any]] = {}
        self._timestamps: Dict[int, float] = {}
    
    def get(self, guild_id: int, key: str) -> Optional[Any]:
        """Get cached value for guild"""
        if guild_id not in self._cache:
            return None
        
        # Check expiry
        if guild_id in self._timestamps:
            if time.time() - self._timestamps[guild_id] > self.ttl:
                del self._cache[guild_id]
                del self._timestamps[guild_id]
                return None
        
        return self._cache[guild_id].get(key)
    
    def set(self, guild_id: int, key: str, value: Any):
        """Set cached value for guild"""
        if guild_id not in self._cache:
            self._cache[guild_id] = {}
            self._timestamps[guild_id] = time.time()
        
        self._cache[guild_id][key] = value
    
    def invalidate_guild(self, guild_id: int):
        """Invalidate all cached data for a guild"""
        self._cache.pop(guild_id, None)
        self._timestamps.pop(guild_id, None)
    
    def invalidate_key(self, guild_id: int, key: str):
        """Invalidate specific key for a guild"""
        if guild_id in self._cache:
            self._cache[guild_id].pop(key, None)
    
    def cleanup_expired(self):
        """Remove all expired entries"""
        now = time.time()
        expired = [gid for gid, ts in self._timestamps.items() if now - ts > self.ttl]
        for gid in expired:
            self._cache.pop(gid, None)
            self._timestamps.pop(gid, None)


class CommandMetrics:
    """
    OPTIMIZATION: Track command performance metrics
    Useful for identifying slow commands
    """
    def __init__(self):
        self._metrics: Dict[str, Dict[str, Any]] = {}
    
    def record(self, command_name: str, execution_time: float, success: bool = True):
        """Record command execution"""
        if command_name not in self._metrics:
            self._metrics[command_name] = {
                "count": 0,
                "total_time": 0.0,
                "min_time": float('inf'),
                "max_time": 0.0,
                "errors": 0
            }
        
        metrics = self._metrics[command_name]
        metrics["count"] += 1
        metrics["total_time"] += execution_time
        metrics["min_time"] = min(metrics["min_time"], execution_time)
        metrics["max_time"] = max(metrics["max_time"], execution_time)
        if not success:
            metrics["errors"] += 1
    
    def get_stats(self, command_name: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a command"""
        if command_name not in self._metrics:
            return None
        
        metrics = self._metrics[command_name]
        return {
            "count": metrics["count"],
            "avg_time": metrics["total_time"] / metrics["count"] if metrics["count"] > 0 else 0,
            "min_time": metrics["min_time"],
            "max_time": metrics["max_time"],
            "errors": metrics["errors"],
            "error_rate": metrics["errors"] / metrics["count"] if metrics["count"] > 0 else 0
        }
    
    def get_slowest(self, limit: int = 10) -> list:
        """Get slowest commands by average execution time"""
        stats = []
        for cmd, metrics in self._metrics.items():
            avg = metrics["total_time"] / metrics["count"] if metrics["count"] > 0 else 0
            stats.append((cmd, avg, metrics["count"]))
        
        stats.sort(key=lambda x: x[1], reverse=True)
        return stats[:limit]
    
    def reset(self):
        """Reset all metrics"""
        self._metrics.clear()


def track_performance(metrics: CommandMetrics):
    """
    OPTIMIZATION: Decorator to track command performance
    
    Usage:
        metrics = CommandMetrics()
        
        @commands.command()
        @track_performance(metrics)
        async def mycommand(ctx):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self_or_ctx, *args, **kwargs):
            # Determine if this is a command or a method
            if isinstance(self_or_ctx, commands.Context):
                ctx = self_or_ctx
                command_name = func.__name__
            else:
                # It's a Cog method
                ctx = args[0] if args else kwargs.get('ctx')
                command_name = func.__name__
            
            start = time.time()
            success = True
            
            try:
                return await func(self_or_ctx, *args, **kwargs)
            except Exception as e:
                success = False
                raise
            finally:
                duration = time.time() - start
                metrics.record(command_name, duration, success)
                
                # Log slow commands
                if duration > 2.0:
                    print(f"⚠ Slow command: {command_name} took {duration:.2f}s")
        
        return wrapper
    return decorator


# Global instances that can be imported and used
guild_cache = GuildDataCache(ttl=300)
command_metrics = CommandMetrics()
memory_monitor = MemoryMonitor(threshold_mb=800)
