"""
ML Strategy Brain - Multi-Path Intelligence System
Learns from every trade to get exponentially smarter

This is the REAL brain that decides:
1. Which strategy to use (2-hop arb, mempool arb, multi-hop, etc.)
2. What parameters to use
3. When to trade vs when to wait
4. How to optimize based on past performance

Features:
- Reinforcement Learning: Learns from profit/loss
- Pattern Recognition: Identifies high-probability opportunities
- Multi-Armed Bandit: Explores new strategies vs exploits known good ones
- Adaptive Parameter Tuning: Adjusts thresholds based on success rate
"""

import numpy as np
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import deque, defaultdict
from datetime import datetime
import logging

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    HAS_PYTORCH = True
except ImportError:
    HAS_PYTORCH = False
    print("⚠️  PyTorch not installed. ML features will use simple heuristics.")
    print("   Install with: pip install torch")

from colorama import Fore, Style, init

init(autoreset=True)
logger = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Record of a completed trade"""
    timestamp: float
    strategy: str  # '2hop_arb', 'mempool_arb', '3hop_arb', etc.
    opportunity: Dict
    decision_params: Dict
    success: bool
    profit_usd: float
    gas_cost_usd: float
    net_profit_usd: float
    execution_time_ms: float
    failure_reason: Optional[str] = None


@dataclass
class StrategyStats:
    """Statistics for a strategy"""
    name: str
    total_attempts: int = 0
    successful: int = 0
    failed: int = 0
    total_profit: float = 0.0
    total_gas: float = 0.0
    avg_profit: float = 0.0
    success_rate: float = 0.0
    profit_per_attempt: float = 0.0


class SimpleOpportunityScorer:
    """
    Simple ML-like scorer when PyTorch not available
    Uses weighted scoring based on historical performance
    """

    def __init__(self):
        self.feature_weights = {
            'gross_profit': 2.0,
            'pool_tvl': 1.0,
            'gas_cost': -1.5,
            'num_hops': -0.5,
            'time_of_day': 0.3,
            'success_rate_history': 3.0
        }

    def score_opportunity(self, features: Dict) -> float:
        """Score an opportunity (0-100)"""
        score = 50.0  # Base score

        # Gross profit contribution
        score += features.get('gross_profit', 0) * self.feature_weights['gross_profit']

        # Pool TVL (higher = more stable)
        tvl = features.get('pool_tvl', 0)
        if tvl > 50000:
            score += 10
        elif tvl > 20000:
            score += 5

        # Gas cost penalty
        score += features.get('gas_cost', 0) * self.feature_weights['gas_cost']

        # Hops penalty (more hops = higher risk)
        hops = features.get('num_hops', 2)
        score += (3 - hops) * abs(self.feature_weights['num_hops']) * 5

        # Time of day (3am-6am UTC = lower volatility)
        hour = datetime.utcnow().hour
        if 3 <= hour <= 6:
            score += 5

        # Historical success rate
        hist_success = features.get('success_rate_history', 0.5)
        score += hist_success * 20

        return max(0, min(100, score))

    def learn_from_outcome(self, features: Dict, outcome: TradeOutcome):
        """Adjust weights based on outcome"""
        if outcome.success and outcome.net_profit_usd > 0:
            # Successful trade - slightly increase weight of features that were high
            for key in self.feature_weights:
                if features.get(key, 0) > 0:
                    self.feature_weights[key] *= 1.01  # 1% increase
        else:
            # Failed trade - slightly decrease weight
            for key in self.feature_weights:
                if features.get(key, 0) > 0:
                    self.feature_weights[key] *= 0.99  # 1% decrease


class NeuralOpportunityScorer(nn.Module):
    """
    PyTorch neural network for opportunity scoring
    Learns from trade outcomes to predict success probability
    """

    def __init__(self, input_size=20):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid()  # Output: 0-1 probability
        )

    def forward(self, x):
        return self.network(x)


class MLStrategyBrain:
    """
    The main ML brain that learns and decides
    Uses multi-armed bandit + reinforcement learning
    """

    STRATEGIES = [
        '2hop_basic_arb',      # Basic 2-hop without mempool
        '2hop_mempool_arb',    # 2-hop with mempool timing
        '3hop_arb',            # 3-hop (if contract supports)
        'wait',                # Wait for better opportunity
    ]

    def __init__(self, trade_db_path='./trade_history.json'):
        self.trade_db_path = trade_db_path
        self.trade_history: deque = deque(maxlen=10000)  # Last 10k trades
        self.strategy_stats: Dict[str, StrategyStats] = {}
        self.opportunity_count = 0

        # Initialize strategy stats
        for strategy in self.STRATEGIES:
            self.strategy_stats[strategy] = StrategyStats(name=strategy)

        # Multi-Armed Bandit parameters
        self.epsilon = 0.1  # 10% exploration rate
        self.epsilon_decay = 0.9999  # Slowly reduce exploration

        # Initialize ML scorer
        if HAS_PYTORCH:
            self.scorer = NeuralOpportunityScorer()
            self.optimizer = optim.Adam(self.scorer.parameters(), lr=0.001)
            self.criterion = nn.BCELoss()
            logger.info(f"{Fore.GREEN}✅ Neural network scorer initialized{Style.RESET_ALL}")
        else:
            self.scorer = SimpleOpportunityScorer()
            logger.info(f"{Fore.YELLOW}⚠️  Using simple scorer (install PyTorch for neural network){Style.RESET_ALL}")

        # Load historical data
        self._load_history()

        logger.info(f"{Fore.GREEN}✅ ML Strategy Brain initialized{Style.RESET_ALL}")
        logger.info(f"   Trade history: {len(self.trade_history):,} trades")
        logger.info(f"   Strategies: {len(self.STRATEGIES)}")

    def _load_history(self):
        """Load trade history from disk"""
        try:
            with open(self.trade_db_path, 'r') as f:
                data = json.load(f)
                for trade_data in data:
                    outcome = TradeOutcome(**trade_data)
                    self.trade_history.append(outcome)
                    self._update_stats(outcome)
        except FileNotFoundError:
            logger.info("No trade history found. Starting fresh.")
        except Exception as e:
            logger.warning(f"Failed to load trade history: {e}")

    def _save_history(self):
        """Save trade history to disk"""
        try:
            data = [asdict(outcome) for outcome in self.trade_history]
            with open(self.trade_db_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trade history: {e}")

    def _update_stats(self, outcome: TradeOutcome):
        """Update strategy statistics"""
        stats = self.strategy_stats[outcome.strategy]
        stats.total_attempts += 1

        if outcome.success:
            stats.successful += 1
            stats.total_profit += outcome.net_profit_usd
        else:
            stats.failed += 1

        stats.total_gas += outcome.gas_cost_usd
        stats.success_rate = stats.successful / max(stats.total_attempts, 1)
        stats.avg_profit = stats.total_profit / max(stats.successful, 1)
        stats.profit_per_attempt = stats.total_profit / max(stats.total_attempts, 1)

    def _extract_features(self, opportunity: Dict, strategy: str) -> Dict:
        """Extract features from opportunity for ML model"""
        return {
            'gross_profit': opportunity.get('profit_usd', 0) or opportunity.get('gross_profit_usd', 0),
            'trade_size': opportunity.get('trade_size_usd', 0) or opportunity.get('amount_in', 0),
            'num_hops': len(opportunity.get('hops', [])) or len(opportunity.get('route', [])) or 2,
            'pool_tvl': min([h.get('tvl', 0) for h in opportunity.get('hops', [{'tvl': 10000}])]),
            'gas_cost': opportunity.get('gas_cost_usd', 0.3),
            'time_of_day': datetime.utcnow().hour / 24.0,  # Normalized
            'day_of_week': datetime.utcnow().weekday() / 7.0,
            'strategy_success_rate': self.strategy_stats[strategy].success_rate,
            'success_rate_history': self._get_historical_success_rate(opportunity),
        }

    def _get_historical_success_rate(self, opportunity: Dict) -> float:
        """Get historical success rate for similar opportunities"""
        # Simple similarity: same token pair, same DEXs
        similar_trades = [
            t for t in self.trade_history
            if self._are_similar(t.opportunity, opportunity)
        ]

        if not similar_trades:
            return 0.5  # Default

        successful = sum(1 for t in similar_trades if t.success)
        return successful / len(similar_trades)

    def _are_similar(self, opp1: Dict, opp2: Dict) -> bool:
        """Check if two opportunities are similar"""
        # Basic similarity check
        path1 = opp1.get('path', '')
        path2 = opp2.get('path', '')
        return path1 == path2

    def choose_strategy(
        self,
        opportunity: Dict,
        available_strategies: List[str],
        gas_price_gwei: float
    ) -> Tuple[str, float]:
        """
        Choose best strategy for this opportunity
        Uses multi-armed bandit: explore vs exploit

        Returns:
            (strategy_name, confidence_score)
        """
        self.opportunity_count += 1

        # Epsilon-greedy: explore or exploit?
        if np.random.random() < self.epsilon:
            # EXPLORE: Try a random strategy
            strategy = np.random.choice(available_strategies)
            confidence = 0.5
            logger.debug(f"🎲 Exploring: {strategy}")
        else:
            # EXPLOIT: Choose best strategy based on past performance
            strategy_scores = {}

            for strat in available_strategies:
                features = self._extract_features(opportunity, strat)

                # Get ML score
                if HAS_PYTORCH:
                    score = self._neural_score(features)
                else:
                    score = self.scorer.score_opportunity(features) / 100.0

                # Combine with strategy stats
                stats = self.strategy_stats[strat]
                historical_performance = stats.profit_per_attempt

                # Weighted combination
                combined_score = (score * 0.7) + (historical_performance * 0.3)
                strategy_scores[strat] = combined_score

            # Choose best
            strategy = max(strategy_scores, key=strategy_scores.get)
            confidence = strategy_scores[strategy]
            logger.debug(f"🎯 Exploiting: {strategy} (confidence: {confidence:.2f})")

        # Decay epsilon (explore less over time)
        self.epsilon *= self.epsilon_decay

        return strategy, confidence

    def _neural_score(self, features: Dict) -> float:
        """Score opportunity using neural network"""
        # Convert features to tensor
        feature_vector = [
            features['gross_profit'] / 100.0,  # Normalize
            features['trade_size'] / 100000.0,
            features['num_hops'] / 4.0,
            features['pool_tvl'] / 100000.0,
            features['gas_cost'] / 2.0,
            features['time_of_day'],
            features['day_of_week'],
            features['strategy_success_rate'],
            features['success_rate_history'],
        ]

        # Pad to input size
        while len(feature_vector) < 20:
            feature_vector.append(0.0)

        x = torch.tensor(feature_vector, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            score = self.scorer(x).item()

        return score

    def learn_from_trade(self, outcome: TradeOutcome):
        """
        Learn from trade outcome - THIS IS WHERE THE MAGIC HAPPENS!
        """
        logger.info(f"\n{Fore.CYAN}🧠 LEARNING FROM TRADE{Style.RESET_ALL}")
        logger.info(f"   Strategy: {outcome.strategy}")
        logger.info(f"   Success: {outcome.success}")
        logger.info(f"   Net Profit: ${outcome.net_profit_usd:.2f}")

        # Add to history
        self.trade_history.append(outcome)

        # Update stats
        self._update_stats(outcome)

        # Train neural network (if available)
        if HAS_PYTORCH and len(self.trade_history) > 100:
            self._train_neural_network(outcome)

        # Train simple scorer
        if not HAS_PYTORCH:
            features = self._extract_features(outcome.opportunity, outcome.strategy)
            self.scorer.learn_from_outcome(features, outcome)

        # Save periodically
        if len(self.trade_history) % 10 == 0:
            self._save_history()

        # Print learning progress
        stats = self.strategy_stats[outcome.strategy]
        logger.info(f"   Strategy stats: {stats.successful}/{stats.total_attempts} success ({stats.success_rate*100:.1f}%)")
        logger.info(f"   Avg profit/trade: ${stats.profit_per_attempt:.2f}")

    def _train_neural_network(self, outcome: TradeOutcome):
        """Train neural network on recent outcomes"""
        # Use last 100 trades for training
        recent_trades = list(self.trade_history)[-100:]

        for trade in recent_trades:
            features = self._extract_features(trade.opportunity, trade.strategy)

            # Convert to tensor
            x = torch.tensor([
                features['gross_profit'] / 100.0,
                features['trade_size'] / 100000.0,
                features['num_hops'] / 4.0,
                features['pool_tvl'] / 100000.0,
                features['gas_cost'] / 2.0,
                features['time_of_day'],
                features['day_of_week'],
                features['strategy_success_rate'],
                features['success_rate_history'],
            ] + [0.0] * 11, dtype=torch.float32).unsqueeze(0)

            # Target: 1.0 if successful and profitable, 0.0 otherwise
            y = torch.tensor([1.0 if trade.success and trade.net_profit_usd > 0 else 0.0])

            # Train
            self.optimizer.zero_grad()
            pred = self.scorer(x)
            loss = self.criterion(pred, y)
            loss.backward()
            self.optimizer.step()

        logger.debug(f"   Neural network trained on {len(recent_trades)} recent trades")

    def get_strategy_recommendation(
        self,
        opportunity: Dict,
        gas_price_gwei: float,
        pol_price_usd: float
    ) -> Dict:
        """
        Main decision function - returns complete recommendation
        """
        # Determine available strategies based on opportunity type
        num_hops = len(opportunity.get('hops', [])) or len(opportunity.get('route', [])) or 2

        available_strategies = []
        if num_hops == 2:
            available_strategies.append('2hop_basic_arb')
            # Mempool arb only if mempool data available
            if opportunity.get('from_mempool', False):
                available_strategies.append('2hop_mempool_arb')
        elif num_hops == 3:
            available_strategies.append('3hop_arb')

        available_strategies.append('wait')  # Always an option

        # Choose strategy
        strategy, confidence = self.choose_strategy(
            opportunity,
            available_strategies,
            gas_price_gwei
        )

        # Get features for scoring
        features = self._extract_features(opportunity, strategy)

        # ML score
        if HAS_PYTORCH:
            ml_score = self._neural_score(features)
        else:
            ml_score = self.scorer.score_opportunity(features) / 100.0

        return {
            'recommended_strategy': strategy,
            'confidence': confidence,
            'ml_score': ml_score,
            'features': features,
            'strategy_stats': asdict(self.strategy_stats[strategy]),
            'should_execute': strategy != 'wait' and ml_score > 0.6,
            'reasoning': self._explain_decision(strategy, ml_score, features)
        }

    def _explain_decision(self, strategy: str, ml_score: float, features: Dict) -> str:
        """Generate human-readable explanation"""
        stats = self.strategy_stats[strategy]

        reasons = []
        reasons.append(f"ML confidence: {ml_score*100:.1f}%")
        reasons.append(f"Historical success: {stats.success_rate*100:.1f}% ({stats.successful}/{stats.total_attempts} trades)")
        reasons.append(f"Avg profit/trade: ${stats.profit_per_attempt:.2f}")

        if features['gross_profit'] > 5:
            reasons.append(f"High profit: ${features['gross_profit']:.2f}")
        if features['pool_tvl'] > 50000:
            reasons.append(f"High liquidity: ${features['pool_tvl']:,.0f}")

        return " | ".join(reasons)

    def get_stats_summary(self) -> str:
        """Get summary of all strategies"""
        lines = [
            f"\n{Fore.CYAN}{'='*80}",
            f"🧠 ML STRATEGY BRAIN - LEARNING SUMMARY",
            f"{'='*80}{Style.RESET_ALL}",
            f"   Total trades: {len(self.trade_history):,}",
            f"   Exploration rate: {self.epsilon*100:.2f}%",
            f""
        ]

        for strategy in self.STRATEGIES:
            stats = self.strategy_stats[strategy]
            if stats.total_attempts > 0:
                lines.append(f"   📊 {strategy}:")
                lines.append(f"      Attempts: {stats.total_attempts}")
                lines.append(f"      Success rate: {stats.success_rate*100:.1f}%")
                lines.append(f"      Total profit: ${stats.total_profit:.2f}")
                lines.append(f"      Avg profit/trade: ${stats.profit_per_attempt:.2f}")

        lines.append(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        return '\n'.join(lines)


# Example usage
if __name__ == "__main__":
    brain = MLStrategyBrain()

    # Example opportunity
    test_opp = {
        'path': 'USDC → WETH → USDC',
        'profit_usd': 8.5,
        'trade_size_usd': 15000,
        'hops': [
            {'dex': 'QuickSwap', 'tvl': 50000},
            {'dex': 'SushiSwap', 'tvl': 75000}
        ]
    }

    # Get recommendation
    rec = brain.get_strategy_recommendation(
        test_opp,
        gas_price_gwei=35,
        pol_price_usd=0.40
    )

    print(f"Recommendation: {rec['recommended_strategy']}")
    print(f"Confidence: {rec['confidence']:.2f}")
    print(f"Should execute: {rec['should_execute']}")
    print(f"Reasoning: {rec['reasoning']}")

    # Simulate outcome
    outcome = TradeOutcome(
        timestamp=time.time(),
        strategy=rec['recommended_strategy'],
        opportunity=test_opp,
        decision_params=rec,
        success=True,
        profit_usd=8.5,
        gas_cost_usd=0.32,
        net_profit_usd=8.18,
        execution_time_ms=2500
    )

    # Learn from it
    brain.learn_from_trade(outcome)

    # Show stats
    print(brain.get_stats_summary())
