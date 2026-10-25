| run (1 process, 43 frames x 3-5 reps) | threads | CCL | e2e p50 ms | e2e p95 ms | e2e mean ms | analyze mean ms |
|---|---|---|---|---|---|---|
| pip, 1 thread, default CCL | 1 | default | 304 | 454 | 317 | 268 |
| COOL, 1 thread, default CCL | 1 | default | 305 | 451 | 316 | 265 |
| pip, 1 thread, BBDT | 1 | bbdt | 303 | 452 | 316 | 270 |
| COOL, 1 thread, BBDT | 1 | bbdt | 305 | 451 | 316 | 265 |
| pip, 4 threads, default CCL | 4 | default | 190 | 331 | 209 | 165 |
| pip, 4 threads, BBDT | 4 | bbdt | 190 | 331 | 211 | 164 |
| COOL, 4 threads, BBDT (default CCL crashes) | 4 | bbdt | 183 | 322 | 205 | 155 |
