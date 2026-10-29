"""Multiplex environment preparation and source analysis as independent phases."""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue,Empty
import threading


def overlap(environment,analysis):
    events=Queue();stop=threading.Event();results={}
    def consume(name,factory):
        generator=None
        try:
            generator=factory(stop)
            while not stop.is_set():
                try:event=next(generator)
                except StopIteration as done:
                    events.put(('finished',name,done.value));return
                events.put(('event',name,{**event,'phase':name}))
        except BaseException as error:events.put(('error',name,error))
        finally:
            if generator is not None:generator.close()
    pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='safefix-phase')
    pool.submit(consume,'environment',environment)
    pool.submit(consume,'analysis',analysis)
    try:
        while len(results)<2:
            try:kind,phase,value=events.get(timeout=1)
            except Empty:continue
            if kind=='error':raise value
            if kind=='finished':results[phase]=value
            else:yield value
        return results['environment'],results['analysis']
    finally:
        stop.set()
        pool.shutdown(wait=True,cancel_futures=True)
