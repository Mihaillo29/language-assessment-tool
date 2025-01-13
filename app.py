from flask import Flask, render_template, request, jsonify, session
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
import os, uuid, random, time
from gtts import gTTS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'a_default_secure_key')
model = OllamaLLM(model="llama3.1")
AUDIO_DIR = os.path.join('static', 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)
TOPICS = ["Weather", "Family", "Technology", "Education", "Travel", "Food", "Sports", "Music"]
MAX_ATTEMPTS = 5
# Create prompt templates
generation_prompt = ChatPromptTemplate.from_template("Generate a paragraph based on this topic: {topic}")
feedback_prompt = ChatPromptTemplate.from_template("""
Evaluate the following transcription accuracy:
Original Paragraph: {original_paragraph}
Transcribed Text: {transcribed_text}
Score: {score}/5

Provide brief feedback about the accuracy of the transcription and pronunciation.
""")
#essay
topic_prompt = ChatPromptTemplate.from_template(
    "Generate an interesting writing topic that would make for a good 250-word essay. "
    "The topic should be specific enough to be focused but broad enough to allow for development. "
    "Return only the topic without any additional text or explanation."
)

evaluation_prompt = ChatPromptTemplate.from_template("""
Evaluate the following 250-word essay:

Topic: {topic}
Essay: {essay}

Provide a rating on a scale of 1-5 (where 5 is excellent) based on the following criteria:
- Relevance to the topic
- Organization and structure
- Development of ideas
- Language usage and clarity
- Overall quality

First provide the numerical score as an integer between 1 and 5, then provide a brief constructive feedback explaining the rating.
Format your response exactly as:
SCORE: [number]
FEEDBACK: [your feedback]
""")

generation_Lprompt = ChatPromptTemplate.from_template("Generate a single line sentence based on this topic: {topic}")
feedback_Lprompt = ChatPromptTemplate.from_template("""
Evaluate the following transcription accuracy:
Original Paragraph: {original_paragraph}
Transcribed Text: {transcribed_text}
Score: {score}/5
Provide brief feedback about the accuracy of the transcription and pronunciation.
""")

# Function to generate a paragraph
def generate_paragraph(topic):
    paragraph_chain = generation_prompt | model
    return paragraph_chain.invoke({"topic": topic})

def generate_topic():#essay
    """Generate a writing topic using Ollama"""
    topic_chain = topic_prompt | model
    return topic_chain.invoke({}).strip()

@app.route('/get_topic', methods=['GET'])
def get_topic():
    try:
        topic = generate_topic()
        return jsonify({'topic': topic})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Function to compare and evaluate transcription
def evaluate_accuracyr(generated_paragraph, transcribed_text):
    # Basic comparison of words
    generated_words = generated_paragraph.split()
    transcribed_words = transcribed_text.split()
    
    total_words = len(generated_words)
    correct_words = sum(1 for g, t in zip(generated_words, transcribed_words) if g.lower() == t.lower())
    accuracy = (correct_words / total_words) * 100
    
    # Convert accuracy to 1-5 scale
    score = round((accuracy / 100) * 5)
    
    # Generate feedback using the template
    feedback_chain = feedback_prompt | model
    feedback = feedback_chain.invoke({
        "original_paragraph": generated_paragraph,
        "transcribed_text": transcribed_text,
        "score": score
    })
    
    return score, feedback

def evaluate_essay(topic, essay):
    """Evaluate the essay and return score and feedback"""
    evaluation_chain = evaluation_prompt | model
    response = evaluation_chain.invoke({
        "topic": topic,
        "essay": essay
    })
    
    try:
        lines = response.split('\n')
        score_line = next((line for line in lines if line.startswith('SCORE:')), '')
        feedback_line = next((line for line in lines if line.startswith('FEEDBACK:')), '')
        
        score_text = score_line.replace('SCORE:', '').strip()
        try:
            score = round(float(score_text))
            score = max(1, min(5, score))
        except ValueError:
            print(f"Could not parse score: {score_text}")
            score = 3
        
        feedback = feedback_line.replace('FEEDBACK:', '').strip()
        if not feedback:
            feedback = "No detailed feedback provided."
        
        return score, feedback
    except Exception as e:
        print(f"Error parsing response: {e}")
        print(f"Full response: {response}")
        return 3, "Error processing evaluation. Please try submitting again."


@app.route('/generate', methods=['POST'])
def generate():
    topic = request.form.get('topic')
    if not topic:
        return jsonify({'error': 'No topic provided'}), 400
    
    paragraph = generate_paragraph(topic)
    return jsonify({'paragraph': paragraph})

@app.route('/evaluatereading', methods=['POST'])
def evaluate():
    data = request.json
    generated_paragraph = data.get('paragraph')
    transcribed_text = data.get('transcription')
    
    if not generated_paragraph or not transcribed_text:
        return jsonify({'error': 'Missing required data'}), 400
    
    score, feedback = evaluate_accuracyr(generated_paragraph, transcribed_text)
    
    return jsonify({
        'score': score,
        'feedback': feedback
    })

@app.route('/evaluatewriting', methods=['POST'])
def evaluateR():
    data = request.json
    if not data or 'essay' not in data or 'topic' not in data:
        return jsonify({'error': 'Missing essay or topic'}), 400
    
    essay = data['essay']
    topic = data['topic']
    
    # Update word count validation
    word_count = len(essay.split())
    if word_count < 100:  # Give some flexibility for minimum
        return jsonify({'error': f'Essay is too short. Current word count: {word_count}. Please write at least 200 words.'}), 400
    if word_count > 250:
        return jsonify({'error': f'Essay exceeds 250 words. Current word count: {word_count}.'}), 400
    
    try:
        score, feedback = evaluate_essay(topic, essay)
        return jsonify({
            'score': score,
            'feedback': feedback,
            'wordCount': word_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start-assessment', methods=['POST'])
def start_assessment():
    session['current_attempt'] = 0
    session['scores'] = []
    session['feedbacks'] = []
    return next_task()

@app.route('/next-task', methods=['POST'])
def next_task():
    app.logger.debug(f"Current Attempt: {session.get('current_attempt', 0)}")
    app.logger.debug(f"Scores: {session.get('scores', [])}")
    app.logger.debug(f"Feedbacks: {session.get('feedbacks', [])}")

    if session['current_attempt'] >= MAX_ATTEMPTS:
        final_score = sum(session['scores']) / len(session['scores']) if session['scores'] else 0
        return jsonify({
            'complete': True,
            'final_score': final_score,
            'feedbacks': session['feedbacks']
        })
    
    topic = random.choice(TOPICS)
    paragraph = generate_Lparagraph(topic)
    audio_url = generate_audio(paragraph)

    session['current_attempt'] += 1
    session['current_paragraph'] = paragraph

    return jsonify({
        'attempt': session['current_attempt'],
        'paragraph': paragraph,
        'audio_url': audio_url
    })

def generate_Lparagraph(topic):
    paragraph_chain = generation_Lprompt | model
    return paragraph_chain.invoke({"topic": topic})

def evaluate_Laccuracy(generated_paragraph, transcribed_text):
    generated_words = generated_paragraph.split()
    transcribed_words = transcribed_text.split()
    
    total_words = len(generated_words)
    correct_words = sum(1 for g, t in zip(generated_words, transcribed_words) if g.lower() == t.lower())
    accuracy = (correct_words / total_words) * 100
    score = round((accuracy / 100) * 5)
    
    feedback_chain = feedback_Lprompt | model
    feedback = feedback_chain.invoke({
        "original_paragraph": generated_paragraph,
        "transcribed_text": transcribed_text,
        "score": score
    })
    
    return score, feedback

@app.route('/evaluatelistening', methods=['POST'])
def evaluatelistening():
    task_data = session.get('task_data', [])
    score, feedback = evaluate_Laccuracy(session['current_paragraph'], request.json['transcription'])

    task_data.append({
        'paragraph': session['current_paragraph'],
        'transcription': request.json['transcription'],
        'score': score,
        'feedback': feedback
    })

    session['task_data'] = task_data
    session['scores'].append(score)
    session['feedbacks'].append(feedback)

    if len(session['scores']) == MAX_ATTEMPTS:
        final_score = sum(session['scores']) / len(session['scores'])
        return jsonify({
            'complete': True,
            'final_score': final_score,
            'feedbacks': session['feedbacks'],
            'task_data': task_data
        })

    return jsonify({'score': score, 'feedback': feedback})

def generate_audio(text):
    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    tts = gTTS(text=text, lang='en')
    tts.save(filepath)
    return f"/static/audio/{filename}"

def cleanup_audio():
    for file in os.listdir(AUDIO_DIR):
        filepath = os.path.join(AUDIO_DIR, file)
        if os.path.getmtime(filepath) < time.time() - 3600:
            os.remove(filepath)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/reading')
def reading():
    return render_template('reading.html')

@app.route('/listening')
def listening():
    return render_template('listening.html')

@app.route('/writing')
def writing():
    return render_template('writing.html')

if __name__ == '__main__':
    app.run(debug=True)
