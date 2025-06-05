"""Phase 3 Example - Advanced PyWatt Module

This example demonstrates all Phase 3 features including:
- Advanced communication with intelligent routing and failover
- Streaming support for large data transfers
- Performance monitoring and SLA tracking
- Production-ready optimizations
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from pywatt_sdk import (
    pywatt_module,
    AppState,
    AnnouncedEndpoint,
    
    # Phase 3 Communication features
    ChannelRouter,
    RoutingMatrix,
    RoutingConfig,
    FailoverManager,
    FailoverConfig,
    CircuitBreakerConfig,
    RetryConfig,
    BatchConfig,
    PerformanceConfig,
    
    # Streaming features
    StreamSender,
    StreamReceiver,
    StreamConfig,
    StreamMetadata,
    StreamPriority,
    PriorityMessageQueue,
    RequestMultiplexer,
    
    # Metrics and monitoring
    PerformanceMonitoringSystem,
    SlaConfig,
    AlertConfig,
    AlertType,
    AlertSeverity,
    
    # Database and cache
    DatabaseType,
    CacheType,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AdvancedModuleState:
    """Advanced application state with Phase 3 features."""
    
    def __init__(self):
        self.initialized = False
        self.message_count = 0
        self.stream_sessions: Dict[str, Any] = {}
        self.performance_data: Dict[str, Any] = {}
        
        # Phase 3 components
        self.channel_router: Optional[ChannelRouter] = None
        self.failover_manager: Optional[FailoverManager] = None
        self.priority_queue: Optional[PriorityMessageQueue] = None
        self.request_multiplexer: Optional[RequestMultiplexer] = None
        self.performance_monitor: Optional[PerformanceMonitoringSystem] = None
    
    async def initialize(self) -> None:
        """Initialize advanced features."""
        logger.info("Initializing advanced module state...")
        
        # Initialize routing with custom matrix
        routing_config = RoutingConfig(
            cache_ttl=120.0,
            max_cache_size=2000,
            enable_load_balancing=True,
            learning_rate=0.15,
        )
        self.channel_router = ChannelRouter(routing_config)
        
        # Initialize failover manager
        failover_config = FailoverConfig(
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=30.0,
            ),
            retry=RetryConfig(
                max_attempts=5,
                base_delay=0.5,
                max_delay=60.0,
                backoff_multiplier=2.0,
                jitter_factor=0.2,
            ),
            batch=BatchConfig(
                max_batch_size=50,
                max_batch_delay=0.05,
                max_batch_bytes=512 * 1024,  # 512KB
            ),
            performance=PerformanceConfig(
                enable_compression=True,
                compression_threshold=2048,
                tcp_nodelay=True,
            ),
        )
        self.failover_manager = FailoverManager(failover_config)
        
        # Initialize priority queue
        self.priority_queue = PriorityMessageQueue(max_size=5000)
        
        # Initialize request multiplexer
        self.request_multiplexer = RequestMultiplexer(request_timeout=45.0)
        
        # Initialize performance monitoring
        sla_config = SlaConfig(
            target_availability=0.995,  # 99.5%
            max_latency=0.2,  # 200ms
            target_throughput=2000.0,  # 2000 messages/sec
            max_error_rate=0.005,  # 0.5%
        )
        alert_config = AlertConfig(
            latency_threshold=0.3,  # 300ms
            error_rate_threshold=0.02,  # 2%
            availability_threshold=0.98,  # 98%
        )
        self.performance_monitor = PerformanceMonitoringSystem(sla_config, alert_config)
        
        self.initialized = True
        logger.info("Advanced module state initialized successfully")


@pywatt_module(
    secrets=["DATABASE_URL", "JWT_SECRET", "REDIS_URL", "ANALYTICS_API_KEY"],
    rotate=True,
    endpoints=[
        AnnouncedEndpoint(path="/health", methods=["GET"], auth=None),
        AnnouncedEndpoint(path="/metrics", methods=["GET"], auth=None),
        AnnouncedEndpoint(path="/api/data", methods=["GET", "POST"], auth="jwt"),
        AnnouncedEndpoint(path="/api/stream", methods=["POST"], auth="jwt"),
        AnnouncedEndpoint(path="/api/upload", methods=["POST"], auth="jwt"),
        AnnouncedEndpoint(path="/api/download/{file_id}", methods=["GET"], auth="jwt"),
        AnnouncedEndpoint(path="/api/analytics", methods=["GET"], auth="jwt"),
        AnnouncedEndpoint(path="/api/performance", methods=["GET"], auth="jwt"),
    ],
    health="/health",
    metrics=True,
    version="v1",
    state_builder=lambda init_data, secrets: AdvancedModuleState(),
    
    # Phase 3 advanced features
    enable_database=True,
    database_config={
        "type": DatabaseType.POSTGRESQL,
        "host": "localhost",
        "database": "advanced_module",
        "pool_config": {
            "min_connections": 5,
            "max_connections": 20,
        }
    },
    enable_cache=True,
    cache_config={
        "type": CacheType.REDIS,
        "host": "localhost",
        "port": 6379,
        "pool_config": {
            "max_connections": 10,
        }
    },
    enable_jwt=True,
    jwt_config={
        "secret_key": "your-secret-key",
        "algorithm": "HS256",
        "expiration": 3600,
    },
    enable_streaming=True,
    streaming_config={
        "max_chunk_size": 128 * 1024,  # 128KB
        "window_size": 15,
        "enable_compression": True,
    },
    enable_metrics=True,
    enable_advanced_routing=True,
    enable_failover=True,
    enable_performance_monitoring=True,
)
async def create_app(state: AppState[AdvancedModuleState]) -> FastAPI:
    """Create and configure the advanced FastAPI application."""
    
    app = FastAPI(
        title="Advanced PyWatt Module",
        description="Demonstrating Phase 3 features",
        version="1.0.0",
    )
    
    # Initialize custom state
    await state.user_state.initialize()
    
    @app.get("/health")
    async def health_check():
        """Enhanced health check with performance metrics."""
        if state.user_state.performance_monitor:
            metrics = await state.user_state.performance_monitor.get_all_metrics()
            sla_status = await state.user_state.performance_monitor.get_all_sla_status()
            
            return {
                "status": "healthy",
                "module": "advanced-pywatt-module",
                "initialized": state.user_state.initialized,
                "message_count": state.user_state.message_count,
                "performance": {
                    "metrics_available": len(metrics),
                    "sla_compliant": all(status.compliant for status in sla_status.values()),
                },
                "timestamp": datetime.now().isoformat(),
            }
        
        return {
            "status": "healthy",
            "module": "advanced-pywatt-module",
            "initialized": state.user_state.initialized,
        }
    
    @app.get("/metrics")
    async def get_metrics():
        """Get comprehensive performance metrics."""
        if not state.user_state.performance_monitor:
            raise HTTPException(status_code=503, detail="Performance monitoring not available")
        
        metrics = await state.user_state.performance_monitor.get_all_metrics()
        sla_status = await state.user_state.performance_monitor.get_all_sla_status()
        comparison = await state.user_state.performance_monitor.get_performance_comparison()
        
        return {
            "metrics": {
                channel.value: {
                    "messages_sent": metric.messages_sent,
                    "messages_received": metric.messages_received,
                    "error_rate": metric.error_rate,
                    "avg_latency_ms": metric.avg_latency_ms,
                    "p95_latency_ms": metric.p95_latency_ms,
                    "throughput_mps": metric.throughput_mps,
                    "availability": metric.availability,
                }
                for channel, metric in metrics.items()
            },
            "sla_status": {
                channel.value: {
                    "compliant": status.compliant,
                    "availability": status.availability_status.compliant,
                    "latency": status.latency_status.compliant,
                    "throughput": status.throughput_status.compliant,
                    "error_rate": status.error_rate_status.compliant,
                }
                for channel, status in sla_status.items()
            },
            "best_performers": {
                "latency": comparison.best_latency[0].value if comparison.best_latency else None,
                "throughput": comparison.best_throughput[0].value if comparison.best_throughput else None,
                "availability": comparison.best_availability[0].value if comparison.best_availability else None,
            },
            "generated_at": comparison.generated_at.isoformat(),
        }
    
    @app.get("/api/data")
    async def get_data(
        limit: int = 10,
        priority: str = "normal",
        app_state: AppState[AdvancedModuleState] = Depends(lambda: state)
    ):
        """Get data with intelligent routing and caching."""
        
        # Use advanced caching with TTL
        cache_key = f"data:limit:{limit}:priority:{priority}"
        cached_data = await app_state.cache_get(cache_key)
        
        if cached_data:
            logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # Simulate database query with connection pooling
        try:
            data = await app_state.execute_query(
                "SELECT id, name, created_at FROM items ORDER BY created_at DESC LIMIT $1",
                [limit]
            )
            
            result = {
                "data": [dict(row) for row in data] if data else [],
                "count": len(data) if data else 0,
                "priority": priority,
                "cached": False,
                "timestamp": datetime.now().isoformat(),
            }
            
            # Cache with priority-based TTL
            ttl = 300 if priority == "high" else 600  # 5 or 10 minutes
            await app_state.cache_set(cache_key, result, ttl=ttl)
            
            app_state.user_state.message_count += 1
            return result
            
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise HTTPException(status_code=500, detail="Database query failed")
    
    @app.post("/api/data")
    async def create_data(
        data: Dict[str, Any],
        app_state: AppState[AdvancedModuleState] = Depends(lambda: state)
    ):
        """Create data with transaction support and message queuing."""
        
        try:
            # Use database transaction
            async with app_state.database.transaction() as tx:
                # Insert data
                result = await tx.execute(
                    "INSERT INTO items (name, data) VALUES ($1, $2) RETURNING id",
                    [data.get("name"), data]
                )
                
                item_id = result[0]["id"] if result else None
                
                # Queue notification message with priority
                if state.user_state.priority_queue:
                    from pywatt_sdk.communication import EncodedMessage
                    notification = EncodedMessage(
                        f"Item created: {item_id}".encode()
                    )
                    await state.user_state.priority_queue.enqueue(
                        notification, 
                        StreamPriority.HIGH
                    )
                
                await tx.commit()
                
                # Invalidate related cache entries
                await app_state.cache.delete("data:*")
                
                app_state.user_state.message_count += 1
                
                return {
                    "id": item_id,
                    "message": "Data created successfully",
                    "queued_notification": True,
                }
                
        except Exception as e:
            logger.error(f"Data creation failed: {e}")
            raise HTTPException(status_code=500, detail="Data creation failed")
    
    @app.post("/api/upload")
    async def upload_file(
        file: UploadFile = File(...),
        app_state: AppState[AdvancedModuleState] = Depends(lambda: state)
    ):
        """Upload large files using streaming."""
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        try:
            # Read file content
            content = await file.read()
            
            # Create stream metadata
            metadata = StreamMetadata(
                total_size=len(content),
                content_type=file.content_type,
                priority=StreamPriority.NORMAL,
                properties={
                    "filename": file.filename,
                    "upload_time": datetime.now().isoformat(),
                }
            )
            
            # Configure streaming
            stream_config = StreamConfig(
                max_chunk_size=64 * 1024,  # 64KB chunks
                window_size=10,
                enable_compression=True,
                compression_threshold=1024,
            )
            
            # Store file info in database
            file_id = await app_state.execute_query(
                "INSERT INTO files (filename, size, content_type) VALUES ($1, $2, $3) RETURNING id",
                [file.filename, len(content), file.content_type]
            )
            
            # Cache file metadata
            await app_state.cache_set(
                f"file:{file_id}",
                {
                    "filename": file.filename,
                    "size": len(content),
                    "content_type": file.content_type,
                    "uploaded_at": datetime.now().isoformat(),
                },
                ttl=3600
            )
            
            return {
                "file_id": file_id,
                "filename": file.filename,
                "size": len(content),
                "chunks": (len(content) + stream_config.max_chunk_size - 1) // stream_config.max_chunk_size,
                "message": "File uploaded successfully",
            }
            
        except Exception as e:
            logger.error(f"File upload failed: {e}")
            raise HTTPException(status_code=500, detail="File upload failed")
    
    @app.get("/api/download/{file_id}")
    async def download_file(
        file_id: str,
        app_state: AppState[AdvancedModuleState] = Depends(lambda: state)
    ):
        """Download files with streaming response."""
        
        try:
            # Get file metadata from cache first
            file_info = await app_state.cache_get(f"file:{file_id}")
            
            if not file_info:
                # Fallback to database
                result = await app_state.execute_query(
                    "SELECT filename, size, content_type FROM files WHERE id = $1",
                    [file_id]
                )
                
                if not result:
                    raise HTTPException(status_code=404, detail="File not found")
                
                file_info = dict(result[0])
            
            # Simulate file content retrieval (in real app, would read from storage)
            async def generate_file_content():
                chunk_size = 8192
                total_size = file_info["size"]
                sent = 0
                
                while sent < total_size:
                    chunk_size_actual = min(chunk_size, total_size - sent)
                    # In real implementation, read actual file chunks
                    chunk = b"x" * chunk_size_actual
                    sent += chunk_size_actual
                    yield chunk
            
            return StreamingResponse(
                generate_file_content(),
                media_type=file_info.get("content_type", "application/octet-stream"),
                headers={
                    "Content-Disposition": f"attachment; filename={file_info['filename']}",
                    "Content-Length": str(file_info["size"]),
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"File download failed: {e}")
            raise HTTPException(status_code=500, detail="File download failed")
    
    @app.get("/api/analytics")
    async def get_analytics(
        app_state: AppState[AdvancedModuleState] = Depends(lambda: state)
    ):
        """Get analytics with inter-module communication."""
        
        try:
            # Send request to analytics module using request multiplexer
            if state.user_state.request_multiplexer:
                from pywatt_sdk.communication import EncodedMessage
                
                request_data = {
                    "module": "advanced-pywatt-module",
                    "metrics": ["user_activity", "performance"],
                    "timeframe": "1h",
                }
                
                request = EncodedMessage(str(request_data).encode())
                
                # This would normally use a real channel
                # response = await state.user_state.request_multiplexer.send_request(
                #     request, analytics_channel
                # )
                
                # Simulate analytics response
                analytics_data = {
                    "user_activity": {
                        "total_requests": app_state.user_state.message_count,
                        "unique_users": 42,
                        "avg_response_time": 150.5,
                    },
                    "performance": {
                        "cpu_usage": 25.3,
                        "memory_usage": 67.8,
                        "disk_usage": 45.2,
                    },
                    "generated_at": datetime.now().isoformat(),
                }
                
                return analytics_data
            
            return {"error": "Analytics service not available"}
            
        except Exception as e:
            logger.error(f"Analytics request failed: {e}")
            raise HTTPException(status_code=500, detail="Analytics request failed")
    
    @app.get("/api/performance")
    async def get_performance_report(
        app_state: AppState[AdvancedModuleState] = Depends(lambda: state)
    ):
        """Get detailed performance analysis."""
        
        if not state.user_state.performance_monitor:
            raise HTTPException(status_code=503, detail="Performance monitoring not available")
        
        try:
            # Get comprehensive performance data
            comparison = await state.user_state.performance_monitor.get_performance_comparison()
            
            # Get circuit breaker stats if available
            circuit_stats = {}
            if state.user_state.failover_manager:
                circuit_stats = state.user_state.failover_manager.get_circuit_breaker_stats()
            
            return {
                "performance_comparison": {
                    "best_latency": {
                        "channel": comparison.best_latency[0].value if comparison.best_latency else None,
                        "value_ms": comparison.best_latency[1] if comparison.best_latency else None,
                    },
                    "best_throughput": {
                        "channel": comparison.best_throughput[0].value if comparison.best_throughput else None,
                        "value_mps": comparison.best_throughput[1] if comparison.best_throughput else None,
                    },
                    "best_availability": {
                        "channel": comparison.best_availability[0].value if comparison.best_availability else None,
                        "value_percent": comparison.best_availability[1] * 100 if comparison.best_availability else None,
                    },
                },
                "circuit_breakers": {
                    channel.value: {
                        "state": stats.state.value,
                        "failure_count": stats.failure_count,
                        "success_count": stats.success_count,
                        "request_count": stats.request_count,
                    }
                    for channel, stats in circuit_stats.items()
                },
                "queue_stats": {
                    "priority_queue_size": state.user_state.priority_queue.size() if state.user_state.priority_queue else 0,
                    "pending_requests": len(state.user_state.request_multiplexer.pending_requests) if state.user_state.request_multiplexer else 0,
                },
                "generated_at": comparison.generated_at.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Performance report failed: {e}")
            raise HTTPException(status_code=500, detail="Performance report failed")
    
    return app


if __name__ == "__main__":
    # This will be handled by the @pywatt_module decorator
    pass 