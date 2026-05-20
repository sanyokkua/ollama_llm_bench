"""Embedded prompt texts and output instructions for Performance run mode.

Each input-size tier is calibrated to a target token count so that models
process meaningfully different amounts of context. Output instructions are
appended verbatim to guide how much the model must generate.
"""

from ollama_llm_bench.backend.core.models import PromptInputSize, PromptOutputSize

# ---------------------------------------------------------------------------
# Input-size prompt texts
# ---------------------------------------------------------------------------

_TINY = """\
What is photosynthesis? Briefly explain the biological process, identify the \
key reactants and products, describe where in the cell it occurs, and explain \
why this process is essential for most life on Earth.\
"""

_SMALL = """\
The history of computing spans several centuries, beginning with mechanical \
calculating machines and culminating in the modern digital computers that power \
nearly every aspect of contemporary life. Charles Babbage designed the first \
mechanical computer, the Difference Engine, in the 1820s, though it was never \
fully built during his lifetime. Alan Turing laid the theoretical groundwork for \
modern computers in the 1930s with his concept of the universal Turing machine. \
The first fully electronic computers, such as ENIAC, were built in the 1940s and \
occupied entire rooms. The invention of the transistor in 1947 and the integrated \
circuit in 1958 dramatically shrank computers while dramatically increasing their \
processing power and reliability. The personal computer revolution of the 1970s \
and 1980s brought computing into homes and offices worldwide, changing nearly \
every industry and profession.

Based on this passage, explain how key inventions such as the transistor and the \
integrated circuit changed the trajectory of computing history, and describe the \
long-term societal impact of the personal computer revolution.\
"""

_MEDIUM = """\
Climate change refers to long-term shifts in global temperatures and weather \
patterns. While some climate variation is natural, since the mid-20th century \
human activities—primarily the burning of fossil fuels—have been the dominant \
driver of the observed changes. The release of greenhouse gases such as carbon \
dioxide and methane traps heat in the atmosphere through a mechanism known as \
the greenhouse effect, causing average global temperatures to rise.

The consequences of climate change are wide-ranging. Rising sea levels threaten \
coastal communities and island nations. Extreme weather events, including \
hurricanes, floods, droughts, and heatwaves, are becoming more frequent and \
more severe. Ecosystems are disrupted as species struggle to adapt to shifting \
habitats: coral reefs bleach as ocean temperatures rise, glaciers retreat, \
and polar ice diminishes. Agriculture is affected as traditional growing seasons \
shift and water availability becomes less predictable.

International efforts to address climate change include the 1997 Kyoto Protocol, \
which set binding emission reduction targets for developed nations, and the 2015 \
Paris Agreement, in which nearly every country committed to limiting warming to \
well below 2 degrees Celsius above pre-industrial levels. However, current \
national pledges fall short of the reductions scientists say are necessary to \
avoid the most severe impacts.

Mitigation strategies include transitioning to renewable energy sources such as \
solar and wind power, improving energy efficiency in buildings and transportation, \
reforestation, and developing carbon capture technologies. Adaptation measures \
aim to help communities cope with changes already locked in, such as building \
sea walls, developing drought-resistant crops, and updating urban infrastructure \
to handle more intense rainfall.

Individual action also plays a role. Reducing energy consumption, shifting to \
plant-based diets, minimizing air travel, and supporting climate-conscious \
policies all contribute to limiting emissions. Scientists emphasize that \
addressing climate change requires systemic change at the level of governments, \
industries, and international cooperation, but that individual choices can \
reinforce broader cultural and political momentum.

Based on the passage above, provide a comprehensive analysis of the causes of \
climate change, the range of documented consequences, the international policy \
responses that have been attempted, and the main strategies proposed for both \
mitigation and adaptation. Evaluate the strengths and limitations of these \
approaches and suggest what additional steps might be necessary.\
"""

_LARGE = """\
The Renaissance was a period of European cultural, artistic, political, and \
intellectual rebirth that followed the Middle Ages. Originating in Italy during \
the 14th century, it later spread throughout Europe, lasting into the 17th century. \
The term "Renaissance" derives from the Italian word for "rebirth," reflecting the \
era's renewed interest in the classical knowledge of ancient Greece and Rome.

ORIGINS AND SPREAD

The Renaissance began in the prosperous city-states of northern Italy, particularly \
Florence, Venice, and Milan. These cities were wealthy commercial centers whose \
merchant classes accumulated enough capital to become patrons of the arts and \
scholarship. Florence, under the Medici banking family, became the intellectual \
heart of the early Renaissance. The Medicis funded artists, architects, poets, \
and philosophers, creating an environment in which humanist ideas could flourish.

The rediscovery of ancient manuscripts—aided by the fall of Constantinople in 1453, \
which drove Greek scholars westward—provided European thinkers with classical texts \
previously unavailable in Western Europe. Humanist scholars such as Petrarch and \
Boccaccio championed the study of classical literature, history, and philosophy, \
arguing that understanding the ancient world was essential to understanding humanity \
itself.

The invention of the movable-type printing press by Johannes Gutenberg around 1440 \
dramatically accelerated the spread of Renaissance ideas. Books that once required \
months to copy by hand could now be produced in days. This democratization of \
knowledge allowed ideas to cross borders rapidly and laid the groundwork for broader \
literacy in Europe.

ART AND ARCHITECTURE

Renaissance art is distinguished by its emphasis on naturalism, perspective, and \
the human form. Artists began to study anatomy directly, dissecting cadavers to \
understand the body's structure, and developed mathematical systems of linear \
perspective to represent three-dimensional space convincingly on two-dimensional \
surfaces. Key figures include Leonardo da Vinci, whose notebooks reveal an \
insatiable curiosity spanning art, science, and engineering; Michelangelo, whose \
sculptures such as the David and paintings on the Sistine Chapel ceiling set \
standards of idealized human beauty; and Raphael, whose frescoes in the Vatican \
Palace exemplify Renaissance harmony and balance.

Architecture returned to classical principles of symmetry, proportion, and the \
use of columns, arches, and domes derived from ancient Rome and Greece. Filippo \
Brunelleschi's dome atop the Florence Cathedral—an engineering feat that had \
stumped builders for over a century—demonstrated that Renaissance artists and \
architects were not merely imitating antiquity but innovating upon it.

SCIENCE AND PHILOSOPHY

The Renaissance also marked the beginning of a scientific revolution. Nicolaus \
Copernicus published his heliocentric model of the solar system in 1543, \
challenging the centuries-old geocentric view endorsed by the Church. Galileo \
Galilei later used telescopic observations to support Copernican theory, bringing \
him into direct conflict with religious authorities. Francis Bacon articulated \
an early version of the scientific method, emphasizing empirical observation and \
experimentation over reliance on ancient authority.

Humanist philosophy shifted attention from exclusively theological concerns to \
the study of human nature, ethics, and potential. Thinkers such as Erasmus of \
Rotterdam and Thomas More used classical learning to critique social institutions \
and advocate for reform. Niccolò Machiavelli's "The Prince" represented a new \
approach to political philosophy—analyzing power as it actually functions rather \
than as it ideally should.

LEGACY

The Renaissance fundamentally altered European civilization. It produced an \
extraordinary body of art and literature that continues to influence Western \
culture. It fostered a spirit of inquiry that would eventually give rise to the \
Scientific Revolution and the Enlightenment. It challenged the intellectual \
authority of the Church in ways that contributed to the Protestant Reformation. \
And it established the idea that human beings, through reason and creativity, \
could reshape their world—a conviction that would define much of Western thought \
in the centuries to come.

Based on the full passage above, write a detailed essay covering: (1) the economic \
and political conditions that allowed the Renaissance to emerge in Italy, \
(2) the role of patronage and the printing press in spreading Renaissance ideas, \
(3) the major artistic and architectural innovations of the period and the key \
figures responsible for them, (4) how Renaissance thought changed science and \
philosophy, and (5) the lasting legacy of the Renaissance on Western civilization.\
"""

_HUGE = """\
THE HISTORY AND SCIENCE OF ARTIFICIAL INTELLIGENCE

INTRODUCTION

Artificial intelligence (AI) refers to the simulation of human-like intelligence \
in machines, enabling them to perform tasks that would typically require human \
cognition—such as understanding language, recognizing images, making decisions, \
and solving complex problems. Over the past several decades, AI has evolved from \
a speculative concept in science fiction into one of the most consequential \
technologies in human history. Today it shapes medicine, transportation, education, \
finance, manufacturing, and nearly every other domain of human activity.

This document provides a comprehensive overview of the history of artificial \
intelligence, the scientific principles and mathematical foundations underlying \
modern AI systems, the major techniques and architectures in use today, the \
most significant applications across industries, and the ethical, societal, and \
policy challenges that the technology presents.

PART I: HISTORY OF ARTIFICIAL INTELLIGENCE

Early Concepts and Theoretical Foundations (Pre-1950)

The idea that machines might think dates to antiquity. Ancient myths described \
mechanical servants and automata, while 17th-century philosophers such as René \
Descartes speculated about whether mechanical devices could ever replicate human \
thought. The formal mathematical foundations for AI emerged in the early 20th \
century. George Boole's algebra of logic in the 19th century, Gottlob Frege's \
predicate logic, and Bertrand Russell and Alfred North Whitehead's "Principia \
Mathematica" together established a formal system for representing and manipulating \
knowledge symbolically—a prerequisite for computational reasoning.

In 1936, Alan Turing introduced the concept of the "universal computing machine" \
in his seminal paper "On Computable Numbers," demonstrating that any well-defined \
algorithm could in principle be executed by a sufficiently capable machine. In 1950, \
Turing proposed the "Turing Test"—the idea that a machine should be considered \
intelligent if a human interrogator could not reliably distinguish its responses \
from those of a human. This framing of intelligence through behavioral imitation \
remained influential for decades.

The Birth of the Field (1950s-1960s)

The term "artificial intelligence" was coined by John McCarthy in 1956 at the \
Dartmouth Conference, widely regarded as the founding event of AI as a discipline. \
McCarthy, along with Marvin Minsky, Claude Shannon, and Nathaniel Rochester, \
organized the conference around the hypothesis that "every aspect of learning or \
any other feature of intelligence can in principle be so precisely described that \
a machine can be made to simulate it." This optimism drove early research.

Early AI programs such as the Logic Theorist (1955) and the General Problem Solver \
(1957), both developed by Allen Newell and Herbert Simon, demonstrated that \
computers could prove mathematical theorems and solve well-defined problems by \
searching through possibilities. LISP, created by McCarthy in 1958, became the \
dominant programming language for AI research for decades.

The first chatbot, ELIZA, was created at MIT by Joseph Weizenbaum in 1966. By \
pattern-matching user input against a set of rules, ELIZA simulated a \
psychotherapist, revealing both the power and the limitations of rule-based \
approaches. Many users were astonished by how human ELIZA seemed, despite its \
mechanical operation.

The First AI Winter (1970s-1980s)

Early successes created inflated expectations. When AI systems failed to scale \
to real-world complexity—unable to handle ambiguity, noise, and the vast \
knowledge required for everyday tasks—funding and interest collapsed. This \
contraction, known as the "first AI winter," prompted a reassessment of \
foundational assumptions.

The development of expert systems in the 1970s and 1980s represented a pragmatic \
response. Rather than attempting general intelligence, these systems encoded the \
knowledge of human experts in specific domains—medical diagnosis, chemical \
analysis, financial planning—as rules in a knowledge base. MYCIN, developed at \
Stanford for diagnosing bacterial infections, demonstrated that AI could perform \
at or above the level of human specialists in well-defined expert domains.

The Second AI Winter and the Rise of Machine Learning (Late 1980s-1990s)

Expert systems proved expensive to build, difficult to maintain, and brittle \
outside their intended domains. A second wave of disillusionment followed. \
Meanwhile, a quieter revolution was taking shape in the statistical and \
connectionist traditions. Researchers such as David Rumelhart and James McClelland \
popularized backpropagation—an algorithm allowing multi-layer neural networks to \
learn from data by adjusting the weights of connections between artificial neurons. \
This approach, sometimes called connectionism, treated intelligence as an emergent \
property of massive parallel computation rather than explicit rule encoding.

During the 1990s, support vector machines, decision trees, and probabilistic \
graphical models such as Bayesian networks were developed and applied across \
diverse tasks. IBM's Deep Blue defeated world chess champion Garry Kasparov in \
1997, demonstrating that specialized AI systems could surpass human performance \
in complex but bounded domains. The Internet meanwhile generated unprecedented \
quantities of data, setting the stage for the machine learning explosion that \
was to follow.

The Deep Learning Revolution (2010s-Present)

The modern AI era is defined by deep learning—the use of neural networks with \
many layers trained on massive datasets using powerful graphics processing units \
(GPUs). In 2012, a deep convolutional neural network called AlexNet, developed \
by Alex Krizhevsky, Ilya Sutskever, and Geoffrey Hinton at the University of \
Toronto, won the ImageNet image recognition competition by a margin so large that \
it immediately redirected the entire field. Within a few years, deep learning had \
surpassed human-level performance on image recognition benchmarks.

Recurrent neural networks and Long Short-Term Memory (LSTM) networks, developed \
in the 1990s by Sepp Hochreiter and Jürgen Schmidhuber, enabled breakthroughs in \
speech recognition, machine translation, and natural language processing. The \
introduction of the transformer architecture by Vaswani et al. in 2017 ("Attention \
Is All You Need") marked another inflection point. Transformers use a mechanism \
called self-attention to model relationships between all tokens in a sequence in \
parallel, enabling training on vastly larger datasets and producing models of \
unprecedented capability in language understanding and generation.

Large language models (LLMs) such as GPT-3, GPT-4, PaLM, LLaMA, and Claude \
demonstrated that scaling transformer models to billions or trillions of parameters, \
trained on diverse corpora of text, produces systems with remarkable emergent \
capabilities: fluent prose generation, code writing, mathematical reasoning, \
question answering, and nuanced conversation. Reinforcement learning from human \
feedback (RLHF) further refined these models to align their outputs with human \
preferences and reduce harmful outputs.

PART II: CORE SCIENTIFIC PRINCIPLES

Machine learning is the branch of AI in which systems learn from data rather \
than from explicitly programmed rules. The central task is to find a function \
that maps inputs to outputs by optimizing a loss function—a measure of how \
far the model's predictions deviate from the correct answers—over a large \
training dataset.

Neural networks are composed of layers of artificial neurons, each of which \
computes a weighted sum of its inputs and applies a non-linear activation function. \
Deep networks stack many such layers, allowing the representation of increasingly \
abstract features. Convolutional networks exploit the spatial structure of images. \
Transformer networks exploit sequential relationships in text through self-attention.

Training requires optimization algorithms such as stochastic gradient descent, \
which iteratively adjusts model parameters in the direction that reduces the \
loss. Techniques such as dropout, batch normalization, and residual connections \
have made it possible to train networks of extraordinary depth.

PART III: MAJOR APPLICATIONS

In healthcare, AI assists with medical image analysis, drug discovery, genomic \
interpretation, and clinical decision support. In transportation, autonomous \
vehicles use computer vision, sensor fusion, and reinforcement learning. In \
finance, AI powers algorithmic trading, fraud detection, and credit scoring. \
In education, personalized tutoring systems adapt to individual learners. \
In creative fields, generative models produce images, music, and text.

PART IV: ETHICAL AND SOCIETAL CHALLENGES

AI raises profound ethical questions. Bias in training data can lead to \
discriminatory outcomes. The opacity of deep learning models makes it difficult \
to explain or contest their decisions. Automation displaces workers. Surveillance \
applications threaten privacy. Autonomous weapons raise questions about \
accountability in armed conflict. The concentration of AI capability in a small \
number of large technology companies raises concerns about market power and \
democratic accountability.

Policy responses are evolving. The European Union's AI Act establishes a \
risk-based regulatory framework. The United States has issued executive orders \
on AI safety. International bodies are working toward norms for responsible AI \
development. Researchers in AI safety and alignment work to ensure that as \
systems become more capable, they remain beneficial and controllable.

QUESTION

Based on the full document above, write a comprehensive analytical essay \
covering: (1) the major historical phases of AI development and the key \
figures, events, and technologies associated with each; (2) the core \
scientific and mathematical principles underlying modern machine learning \
and deep learning systems; (3) the most significant current applications \
of AI across at least four distinct industries; (4) the principal ethical \
and societal challenges posed by AI; and (5) the state of current policy \
and regulatory responses to those challenges. Evaluate both the promise \
and the risks of continued AI advancement.\
"""

PERFORMANCE_PROMPTS: dict[PromptInputSize, str] = {
    PromptInputSize.TINY: _TINY,
    PromptInputSize.SMALL: _SMALL,
    PromptInputSize.MEDIUM: _MEDIUM,
    PromptInputSize.LARGE: _LARGE,
    PromptInputSize.HUGE: _HUGE,
}

OUTPUT_INSTRUCTIONS: dict[PromptOutputSize, str] = {
    PromptOutputSize.XS: "\n\nRespond with exactly 1 complete sentence.",
    PromptOutputSize.SM: "\n\nRespond with exactly 5 complete sentences.",
    PromptOutputSize.MD: "\n\nRespond with exactly 20 complete sentences.",
    PromptOutputSize.LG: "\n\nRespond with exactly 100 complete sentences.",
    PromptOutputSize.XL: "\n\nRespond with exactly 500 complete sentences.",
}


INPUT_SIZE_DESCRIPTIONS: dict[PromptInputSize, str] = {
    PromptInputSize.TINY: "XS · Tiny (~40 tokens)",
    PromptInputSize.SMALL: "SM · Short (~250 tokens)",
    PromptInputSize.MEDIUM: "MD · Medium (~550 tokens)",
    PromptInputSize.LARGE: "LG · Long (~1 100 tokens)",
    PromptInputSize.HUGE: "XL · Huge (~2 500 tokens)",
}

OUTPUT_SIZE_DESCRIPTIONS: dict[PromptOutputSize, str] = {
    PromptOutputSize.XS: "XS · 1 sentence",
    PromptOutputSize.SM: "SM · 5 sentences",
    PromptOutputSize.MD: "MD · 20 sentences",
    PromptOutputSize.LG: "LG · 100 sentences",
    PromptOutputSize.XL: "XL · 500 sentences",
}


def build_performance_prompt(input_size: PromptInputSize, output_size: PromptOutputSize) -> str:
    """Return the combined input prompt and output instruction for a performance cell."""
    return PERFORMANCE_PROMPTS[input_size] + OUTPUT_INSTRUCTIONS[output_size]
