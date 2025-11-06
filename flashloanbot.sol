// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

interface IAaveLendingPool {
    function flashLoan(
        address receiverAddress,
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata modes,
        address onBehalfOf,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IDexRouter {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory);
}

interface IBalancerVault {
    function flashLoan(
        address recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;
}

contract FlashloanTradingBot is ReentrancyGuard {
    address public owner;
    IAaveLendingPool public aave;
    IBalancerVault public balancer;

    mapping(address => bool) public authorizedCallers;

    event TradeExecuted(address tokenIn, address tokenOut, uint profit);

    struct TradeParams {
        address tokenIn;
        address tokenOut;
        address dex1;
        address dex2;
        uint256 minProfit;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    modifier onlyAuthorized() {
        require(msg.sender == owner || authorizedCallers[msg.sender], "Not authorized");
        _;
    }

    constructor(address _aave, address _balancer) {
        owner = msg.sender;
        aave = IAaveLendingPool(_aave);
        balancer = IBalancerVault(_balancer);
    }

    function authorizeCaller(address caller, bool status) external onlyOwner {
        authorizedCallers[caller] = status;
    }

    function executeFlashloan(
        address tokenIn,
        address tokenOut,
        address dex1,
        address dex2,
        uint8, // dex1Version - not used but kept for interface compatibility
        uint8, // dex2Version - not used but kept for interface compatibility
        uint256 amountIn,
        uint256 minProfitAmount,
        bytes calldata, // dex1Data - not used but kept for interface compatibility
        bytes calldata  // dex2Data - not used but kept for interface compatibility
    ) external onlyAuthorized nonReentrant {
        address[] memory assets = new address[](1);
        uint256[] memory amounts = new uint256[](1);
        uint256[] memory modes = new uint256[](1);

        assets[0] = tokenIn;
        amounts[0] = amountIn;
        modes[0] = 0;

        bytes memory params = abi.encode(tokenIn, tokenOut, dex1, dex2, minProfitAmount);
        aave.flashLoan(address(this), assets, amounts, modes, address(this), params, 0);
    }

    function executeBalancerFlashloan(
        address tokenIn,
        address tokenOut,
        address dex1,
        address dex2,
        uint8, // dex1Version - not used but kept for interface compatibility
        uint8, // dex2Version - not used but kept for interface compatibility
        uint256 amountIn,
        uint256 minProfitAmount,
        bytes calldata, // dex1Data - not used but kept for interface compatibility
        bytes calldata  // dex2Data - not used but kept for interface compatibility
    ) external onlyAuthorized nonReentrant {
        address[] memory tokens = new address[](1);
        uint256[] memory amounts = new uint256[](1);
        
        tokens[0] = tokenIn;
        amounts[0] = amountIn;
        
        bytes memory params = abi.encode(tokenIn, tokenOut, dex1, dex2, minProfitAmount);
        balancer.flashLoan(address(this), tokens, amounts, params);
    }

    function executeOperation(
        address[] calldata,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == address(aave), "Unauthorized");
        
        TradeParams memory trade;
        (trade.tokenIn, trade.tokenOut, trade.dex1, trade.dex2, trade.minProfit) = 
            abi.decode(params, (address, address, address, address, uint256));

        _executeAaveArbitrage(trade, amounts[0], premiums[0]);
        return true;
    }

    function receiveFlashLoan(
        address[] calldata, // tokens - required by Balancer interface
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata params
    ) external {
        require(msg.sender == address(balancer), "Unauthorized");
        
        TradeParams memory trade;
        (trade.tokenIn, trade.tokenOut, trade.dex1, trade.dex2, trade.minProfit) = 
            abi.decode(params, (address, address, address, address, uint256));

        _executeBalancerArbitrage(trade, amounts[0], feeAmounts[0]);
    }
    
    function _executeAaveArbitrage(
        TradeParams memory trade,
        uint256 borrowedAmount,
        uint256 premium
    ) internal {
        uint256 finalAmount = _swap(trade.tokenIn, trade.tokenOut, trade.dex1, trade.dex2, borrowedAmount);
        uint256 totalOwed = borrowedAmount + premium;
        
        require(finalAmount >= totalOwed + trade.minProfit, "Profit below threshold");
        
        IERC20(trade.tokenIn).approve(address(aave), totalOwed);
        emit TradeExecuted(trade.tokenIn, trade.tokenOut, finalAmount - totalOwed);
    }
    
    function _executeBalancerArbitrage(
        TradeParams memory trade,
        uint256 borrowedAmount,
        uint256 fee
    ) internal {
        uint256 finalAmount = _swap(trade.tokenIn, trade.tokenOut, trade.dex1, trade.dex2, borrowedAmount);
        uint256 totalOwed = borrowedAmount + fee;
        
        require(finalAmount >= totalOwed + trade.minProfit, "Profit below threshold");
        
        IERC20(trade.tokenIn).transfer(address(balancer), totalOwed);
        emit TradeExecuted(trade.tokenIn, trade.tokenOut, finalAmount - totalOwed);
    }
    
    function _swap(
        address tokenIn,
        address tokenOut,
        address dex1,
        address dex2,
        uint256 amountIn
    ) internal returns (uint256) {
        // First swap
        IERC20(tokenIn).approve(dex1, amountIn);
        address[] memory path1 = new address[](2);
        path1[0] = tokenIn;
        path1[1] = tokenOut;
        
        uint[] memory amounts1 = IDexRouter(dex1).swapExactTokensForTokens(
            amountIn, 1, path1, address(this), block.timestamp
        );

        // Second swap
        uint256 midAmount = amounts1[1];
        IERC20(tokenOut).approve(dex2, midAmount);
        address[] memory path2 = new address[](2);
        path2[0] = tokenOut;
        path2[1] = tokenIn;
        
        uint[] memory amounts2 = IDexRouter(dex2).swapExactTokensForTokens(
            midAmount, 1, path2, address(this), block.timestamp
        );
        
        return amounts2[1];
    }

    function withdrawToken(address token) external onlyOwner {
        IERC20(token).transfer(owner, IERC20(token).balanceOf(address(this)));
    }

    function withdrawETH() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        owner = newOwner;
    }

    receive() external payable {}
}