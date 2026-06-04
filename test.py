import sys
sys.path.append('backend')
from modules.agent.service.core.pipelines.registry import PipelineRegistry
open('test_pipe.txt', 'w', encoding='utf-8').write(PipelineRegistry.dispatch('Ligar para Pedro C. Andrade Junior', '', 8154, 1074, None))
