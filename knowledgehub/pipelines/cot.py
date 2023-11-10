from copy import deepcopy
from typing import List

from theflow import Compose, Node, Param

from kotaemon.base import BaseComponent
from kotaemon.llms.chats.openai import AzureChatOpenAI
from kotaemon.prompt.base import BasePromptComponent


class Thought(BaseComponent):
    """A thought in the chain of thought

    - Input: `**kwargs` pairs, where key is the placeholder in the prompt, and
    value is the value.
    - Output: an output dictionary

    _**Usage:**_

    Create and run a thought:

    ```python
    >> from kotaemon.pipelines.cot import Thought
    >> thought = Thought(
         prompt="How to {action} {object}?",
         llm=AzureChatOpenAI(...),
         post_process=lambda string: {"tutorial": string},
       )
    >> output = thought(action="install", object="python")
    >> print(output)
    {'tutorial': 'As an AI language model,...'}
    ```

    Basically, when a thought is run, it will:

    1. Populate the prompt template with the input `**kwargs`.
    2. Run the LLM model with the populated prompt.
    3. Post-process the LLM output with the post-processor.

    This `Thought` allows chaining sequentially with the + operator. For example:

    ```python
    >> llm = AzureChatOpenAI(...)
    >> thought1 = Thought(
           prompt="Word {word} in {language} is ",
           llm=llm,
           post_process=lambda string: {"translated": string},
       )
    >> thought2 = Thought(
            prompt="Translate {translated} to Japanese",
            llm=llm,
            post_process=lambda string: {"output": string},
       )

    >> thought = thought1 + thought2
    >> thought(word="hello", language="French")
    {'word': 'hello',
     'language': 'French',
     'translated': '"Bonjour"',
     'output': 'こんにちは (Konnichiwa)'}
    ```

    Under the hood, when the `+` operator is used, a `ManualSequentialChainOfThought`
    is created.
    """

    prompt: Param[str] = Param(
        help="The prompt template string. This prompt template has Python-like "
        "variable placeholders, that then will be subsituted with real values when "
        "this component is executed"
    )
    llm: Node[BaseComponent] = Node(
        AzureChatOpenAI, help="The LLM model to execute the input prompt"
    )
    post_process: Node[Compose] = Node(
        help="The function post-processor that post-processes LLM output prediction ."
        "It should take a string as input (this is the LLM output text) and return "
        "a dictionary, where the key should"
    )

    @Node.auto(depends_on="prompt")
    def prompt_template(self):
        """Automatically wrap around param prompt. Can ignore"""
        return BasePromptComponent(self.prompt)

    def run(self, **kwargs) -> dict:
        """Run the chain of thought"""
        prompt = self.prompt_template(**kwargs).text
        response = self.llm(prompt).text
        return self.post_process(response)

    def get_variables(self) -> List[str]:
        return []

    def __add__(self, next_thought: "Thought") -> "ManualSequentialChainOfThought":
        return ManualSequentialChainOfThought(
            thoughts=[self, next_thought], llm=self.llm
        )


class ManualSequentialChainOfThought(BaseComponent):
    """Perform sequential chain-of-thought with manual pre-defined prompts

    This method supports variable number of steps. Each step corresponds to a
    `kotaemon.pipelines.cot.Thought`. Please refer that section for
    Thought's detail. This section is about chaining thought together.

    _**Usage:**_

    **Create and run a chain of thought without "+" operator:**

    ```python
    >> from kotaemon.pipelines.cot import Thought, ManualSequentialChainOfThought

    >> llm = AzureChatOpenAI(...)
    >> thought1 = Thought(
           prompt="Word {word} in {language} is ",
           post_process=lambda string: {"translated": string},
       )
    >> thought2 = Thought(
            prompt="Translate {translated} to Japanese",
            post_process=lambda string: {"output": string},
       )
    >> thought = ManualSequentialChainOfThought(thoughts=[thought1, thought2], llm=llm)
    >> thought(word="hello", language="French")
    {'word': 'hello',
     'language': 'French',
     'translated': '"Bonjour"',
     'output': 'こんにちは (Konnichiwa)'}
    ```

    **Create and run a chain of thought without "+" operator:** Please refer the
    `kotaemon.pipelines.cot.Thought` section for examples.

    This chain-of-thought optionally takes a termination check callback function.
    This function will be called after each thought is executed. It takes in a
    dictionary of all thought outputs so far, and it returns True or False. If
    True, the chain-of-thought will terminate. If unset, the default callback always
    returns False.
    """

    thoughts: Param[List[Thought]] = Param(
        default_callback=lambda *_: [], help="List of Thought"
    )
    llm: Param = Param(help="The LLM model to use (base of kotaemon.llms.LLM)")
    terminate: Param = Param(
        default=lambda _: False,
        help="Callback on terminate condition. Default to always return False",
    )

    def run(self, **kwargs) -> dict:
        """Run the manual chain of thought"""

        inputs = deepcopy(kwargs)
        for idx, thought in enumerate(self.thoughts):
            if self.llm:
                thought.llm = self.llm
            self._prepare_child(thought, f"thought{idx}")

            output = thought(**inputs)
            inputs.update(output)
            if self.terminate(inputs):
                break

        return inputs

    def __add__(self, next_thought: Thought) -> "ManualSequentialChainOfThought":
        return ManualSequentialChainOfThought(
            thoughts=self.thoughts + [next_thought], llm=self.llm
        )